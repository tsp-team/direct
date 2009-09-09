// Filename: p3dWinSplashWindow.cxx
// Created by:  drose (17Jun09)
//
////////////////////////////////////////////////////////////////////
//
// PANDA 3D SOFTWARE
// Copyright (c) Carnegie Mellon University.  All rights reserved.
//
// All use of this software is subject to the terms of the revised BSD
// license.  You should have received a copy of this license along
// with this source code in a file named "LICENSE."
//
////////////////////////////////////////////////////////////////////

#include "p3dWinSplashWindow.h"

#ifdef _WIN32

bool P3DWinSplashWindow::_registered_window_class = false;

////////////////////////////////////////////////////////////////////
//     Function: P3DWinSplashWindow::Constructor
//       Access: Public
//  Description: 
////////////////////////////////////////////////////////////////////
P3DWinSplashWindow::
P3DWinSplashWindow(P3DInstance *inst) : 
  P3DSplashWindow(inst)
{
  _thread = NULL;
  _thread_id = 0;
  _hwnd = NULL;
  _progress_bar = NULL;
  _text_label = NULL;
  _thread_running = false;
  _install_label_changed = false;
  _install_progress = 0.0;

  INIT_LOCK(_install_lock);
}

////////////////////////////////////////////////////////////////////
//     Function: P3DWinSplashWindow::Destructor
//       Access: Public, Virtual
//  Description: 
////////////////////////////////////////////////////////////////////
P3DWinSplashWindow::
~P3DWinSplashWindow() {
  stop_thread();

  DESTROY_LOCK(_install_lock);
}

////////////////////////////////////////////////////////////////////
//     Function: P3DWinSplashWindow::set_wparams
//       Access: Public, Virtual
//  Description: Changes the window parameters, e.g. to resize or
//               reposition the window; or sets the parameters for the
//               first time, creating the initial window.
////////////////////////////////////////////////////////////////////
void P3DWinSplashWindow::
set_wparams(const P3DWindowParams &wparams) {
  P3DSplashWindow::set_wparams(wparams);

  if (_thread_id == 0) {
    start_thread();
  }
}

////////////////////////////////////////////////////////////////////
//     Function: P3DWinSplashWindow::set_image_filename
//       Access: Public, Virtual
//  Description: Specifies the name of a JPEG image file that is
//               displayed in the center of the splash window.
////////////////////////////////////////////////////////////////////
void P3DWinSplashWindow::
set_image_filename(const string &image_filename, ImagePlacement image_placement) {
  nout << "image_filename = " << image_filename << ", thread_id = " << _thread_id << "\n";
  WinImageData *image = NULL;
  switch (image_placement) {
  case IP_background:
    image = &_background_image;
    break;

  case IP_button_ready:
    image = &_button_ready_image;
    set_button_range(_button_ready_image);
    break;

  case IP_button_rollover:
    image = &_button_rollover_image;
    break;
   
  case IP_button_click:
    image = &_button_click_image;
    break;
  }
  if (image != NULL) {
    ACQUIRE_LOCK(_install_lock);
    if (image->_filename != image_filename) {
      image->_filename = image_filename;
      image->_filename_changed = true;
    }
    RELEASE_LOCK(_install_lock);
  }

  if (_thread_id != 0) {
    // Post a silly message to spin the message loop.
    PostThreadMessage(_thread_id, WM_USER, 0, 0);

    if (!_thread_running && _thread_continue) {
      // The user must have closed the window.  Let's shut down the
      // instance, too.
      _inst->request_stop();
    }
  }
}

////////////////////////////////////////////////////////////////////
//     Function: P3DWinSplashWindow::set_install_label
//       Access: Public, Virtual
//  Description: Specifies the text that is displayed above the
//               install progress bar.
////////////////////////////////////////////////////////////////////
void P3DWinSplashWindow::
set_install_label(const string &install_label) {
  ACQUIRE_LOCK(_install_lock);
  if (_install_label != install_label) {
    _install_label = install_label;
    _install_label_changed = true;
  }
  RELEASE_LOCK(_install_lock);

  if (_thread_id != 0) {
    // Post a silly message to spin the message loop.
    PostThreadMessage(_thread_id, WM_USER, 0, 0);

    if (!_thread_running && _thread_continue) {
      // The user must have closed the window.  Let's shut down the
      // instance, too.
      _inst->request_stop();
    }
  }
}

////////////////////////////////////////////////////////////////////
//     Function: P3DWinSplashWindow::set_install_progress
//       Access: Public, Virtual
//  Description: Moves the install progress bar from 0.0 to 1.0.
////////////////////////////////////////////////////////////////////
void P3DWinSplashWindow::
set_install_progress(double install_progress) {
  ACQUIRE_LOCK(_install_lock);
  _install_progress = install_progress;
  RELEASE_LOCK(_install_lock);

  if (_thread_id != 0) {
    // Post a silly message to spin the message loop.
    PostThreadMessage(_thread_id, WM_USER, 0, 0);

    if (!_thread_running && _thread_continue) {
      // The user must have closed the window.  Let's shut down the
      // instance, too.
      _inst->request_stop();
    }
  }
}

////////////////////////////////////////////////////////////////////
//     Function: P3DWinSplashWindow::register_window_class
//       Access: Public, Static
//  Description: Registers the window class for this window, if
//               needed.
////////////////////////////////////////////////////////////////////
void P3DWinSplashWindow::
register_window_class() {
  if (!_registered_window_class) {
    HINSTANCE application = GetModuleHandle(NULL);

    WNDCLASS wc;
    ZeroMemory(&wc, sizeof(WNDCLASS));
    wc.lpfnWndProc = st_window_proc;
    wc.hInstance = application;
    wc.hCursor = LoadCursor(NULL, IDC_ARROW);
    wc.lpszClassName = "panda3d_splash";
    
    if (!RegisterClass(&wc)) {
      nout << "Could not register window class panda3d_splash\n";
    }
    _registered_window_class = true;
  }
}

////////////////////////////////////////////////////////////////////
//     Function: P3DWinSplashWindow::unregister_window_class
//       Access: Public, Static
//  Description: Unregisters the window class for this window.  It is
//               necessary to do this before unloading the DLL.
////////////////////////////////////////////////////////////////////
void P3DWinSplashWindow::
unregister_window_class() {
  if (_registered_window_class) {
    HINSTANCE application = GetModuleHandle(NULL);

    if (!UnregisterClass("panda3d_splash", application)) {
      nout << "Could not unregister window class panda3d_splash\n";
    }
    _registered_window_class = false;
  }
}

////////////////////////////////////////////////////////////////////
//     Function: P3DWinSplashWindow::button_click_detected
//       Access: Protected, Virtual
//  Description: Called when a button click by the user is detected in
//               set_mouse_data(), this method simply turns around and
//               notifies the instance.  It's a virtual method to give
//               subclasses a chance to redirect this message to the
//               main thread or process, as necessary.
////////////////////////////////////////////////////////////////////
void P3DWinSplashWindow::
button_click_detected() {
  // Since this message is detected in the sub-thread in the Windows
  // case, we have to protect ourselves from re-entry by grabbing the
  // global _api_lock.
  ACQUIRE_LOCK(_api_lock);
  P3DSplashWindow::button_click_detected();
  RELEASE_LOCK(_api_lock);
}

////////////////////////////////////////////////////////////////////
//     Function: P3DWinSplashWindow::start_thread
//       Access: Private
//  Description: Spawns the sub-thread.
////////////////////////////////////////////////////////////////////
void P3DWinSplashWindow::
start_thread() {
  _thread_continue = true;
  _thread_running = true;
  _thread = CreateThread(NULL, 0, &win_thread_run, this, 0, &_thread_id);
  if (_thread == NULL) {
    // Thread never got started.
    _thread_running = false;
  }
}

////////////////////////////////////////////////////////////////////
//     Function: P3DWinSplashWindow::stop_thread
//       Access: Private
//  Description: Terminates and joins the sub-thread.
////////////////////////////////////////////////////////////////////
void P3DWinSplashWindow::
stop_thread() {
  _thread_continue = false;

  if (_thread_id != 0) {
    // Post a silly message to spin the message loop.
    PostThreadMessage(_thread_id, WM_USER, 0, 0);
  }

  if (_thread != NULL){ 
    WaitForSingleObject(_thread, INFINITE);

    CloseHandle(_thread);
    _thread = NULL;

    // Now that the thread has exited, we can safely close its window.
    // (We couldn't close the window in the thread, because that would
    // cause a deadlock situation--the thread can't acknowledge the
    // window closing until we spin the event loop in the parent
    // thread.)
    close_window();
  }
}

////////////////////////////////////////////////////////////////////
//     Function: P3DWinSplashWindow::thread_run
//       Access: Private
//  Description: The sub-thread's main run method.
////////////////////////////////////////////////////////////////////
void P3DWinSplashWindow::
thread_run() {
  make_window();

  double last_progress = -1.0;

  MSG msg;
  int retval;
  retval = GetMessage(&msg, NULL, 0, 0);
  while (retval != 0 && _thread_continue) {
    if (retval == -1) {
      nout << "Error processing message queue.\n";
      break;
    }
    TranslateMessage(&msg);
    DispatchMessage(&msg);

    ACQUIRE_LOCK(_install_lock);
    double install_progress = _install_progress;

    update_image(_background_image);
    update_image(_button_ready_image);
    update_image(_button_rollover_image);
    update_image(_button_click_image);

    if (_install_label_changed && _progress_bar != NULL) {
      update_install_label(_install_label);
    }
    _install_label_changed = false;

    if (_drawn_bstate != _bstate) {
      // The button has changed state.  Redraw it.
      _drawn_bstate = _bstate;
      InvalidateRect(_hwnd, NULL, TRUE);
    }
    RELEASE_LOCK(_install_lock);

    if (install_progress != last_progress) {
      int progress = (int)(install_progress * 100.0);
      if (_progress_bar == NULL) {
        // Is it time to create the progress bar?
        if (progress != 0) {
          make_progress_bar();
        }
      } else {
        // Update the progress bar.  We do this only within the
        // thread, to ensure we don't get a race condition when
        // starting or closing the thread.
        SendMessage(_progress_bar, PBM_SETPOS, progress, 0);
        
        last_progress = install_progress;
      }
    }

    retval = GetMessage(&msg, NULL, 0, 0);
  }

  // Tell our parent thread that we're done.
  _thread_running = false;
}

////////////////////////////////////////////////////////////////////
//     Function: P3DWinSplashWindow::win_thread_run
//       Access: Private, Static
//  Description: The OS-specific thread callback function.
////////////////////////////////////////////////////////////////////
DWORD P3DWinSplashWindow::
win_thread_run(LPVOID data) {
  ((P3DWinSplashWindow *)data)->thread_run();
  return 0;
}

////////////////////////////////////////////////////////////////////
//     Function: P3DWinSplashWindow::make_window
//       Access: Private
//  Description: Creates the window for displaying progress.  Runs
//               within the sub-thread.
////////////////////////////////////////////////////////////////////
void P3DWinSplashWindow::
make_window() {
  register_window_class();
  HINSTANCE application = GetModuleHandle(NULL);
  
  int x = CW_USEDEFAULT;
  int y = CW_USEDEFAULT;
  if (_wparams.get_win_x() != 0 && _wparams.get_win_y() != 0) {
    x = _wparams.get_win_x();
    y = _wparams.get_win_y();
  }
  
  int width = 320;
  int height = 240;
  if (_wparams.get_win_width() != 0 && _wparams.get_win_height() != 0) {
    width = _wparams.get_win_width();
    height = _wparams.get_win_height();
  }

  if (_wparams.get_window_type() == P3D_WT_embedded) {
    // Create an embedded window.
    DWORD window_style = 
      WS_CHILD | WS_CLIPCHILDREN | WS_CLIPSIBLINGS;

    HWND parent_hwnd = _wparams.get_parent_window()._hwnd;

    _hwnd = 
      CreateWindow("panda3d_splash", "Panda3D", window_style,
                   x, y, width, height,
                   parent_hwnd, NULL, application, 0);
    
    if (!_hwnd) {
      nout << "Could not create embedded window!\n";
      return;
    }

  } else {
    // Create a toplevel window.
    DWORD window_style = 
      WS_POPUP | WS_CLIPCHILDREN | WS_CLIPSIBLINGS |
      WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX |
      WS_SIZEBOX | WS_MAXIMIZEBOX;
    
    _hwnd = 
      CreateWindow("panda3d_splash", "Panda3D", window_style,
                   x, y, width, height,
                   NULL, NULL, application, 0);
    if (!_hwnd) {
      nout << "Could not create toplevel window!\n";
      return;
    }
  }
  SetWindowLongPtr(_hwnd, GWLP_USERDATA, (LONG_PTR)this);
  ShowWindow(_hwnd, SW_SHOWNORMAL);
}


////////////////////////////////////////////////////////////////////
//     Function: P3DWinSplashWindow::make_progress_bar
//       Access: Private
//  Description: Creates the progress bar and label.  Runs
//               within the sub-thread.  This is done a few seconds
//               after the main window is created, to give us a chance
//               to launch quickly without bothering the user.
////////////////////////////////////////////////////////////////////
void P3DWinSplashWindow::
make_progress_bar() {
  if (_progress_bar != NULL) {
    return;
  }

  ACQUIRE_LOCK(_install_lock);
  string install_label = _install_label;
  double install_progress = _install_progress;
  _install_label_changed = false;
  RELEASE_LOCK(_install_lock);

  HINSTANCE application = GetModuleHandle(NULL);
  DWORD window_style = 
    WS_CHILD | WS_CLIPCHILDREN | WS_CLIPSIBLINGS;

  int bar_x, bar_y, bar_width, bar_height;
  get_bar_placement(bar_x, bar_y, bar_width, bar_height);

  _progress_bar = 
    CreateWindowEx(0, PROGRESS_CLASS, "", window_style,
                   bar_x, bar_y, bar_width, bar_height,
                   _hwnd, NULL, application, 0);
  SendMessage(_progress_bar, PBM_SETPOS, (int)(install_progress * 100.0), 0);
  ShowWindow(_progress_bar, SW_SHOWNORMAL);

  update_install_label(install_label);
}


////////////////////////////////////////////////////////////////////
//     Function: P3DWinSplashWindow::update_install_label
//       Access: Private
//  Description: Changes the text on the install label.  Runs within
//               the sub-thread.
////////////////////////////////////////////////////////////////////
void P3DWinSplashWindow::
update_install_label(const string &install_label) {
  assert(_progress_bar != NULL);

  if (_text_label != NULL) {
    DestroyWindow(_text_label);
    _text_label = NULL;
  }

  if (install_label.empty()) {
    // Trivial case.
    return;
  }

  // Create a static text label.  What a major pain *this* is.

  const char *text = install_label.c_str();
  HFONT font = (HFONT)GetStockObject(ANSI_VAR_FONT); 

  HDC dc = GetDC(_hwnd);
  SelectObject(dc, font);
  SIZE text_size;
  GetTextExtentPoint32(dc, text, strlen(text), &text_size);
  ReleaseDC(_hwnd, dc);

  HINSTANCE application = GetModuleHandle(NULL);
  DWORD window_style = 
    SS_OWNERDRAW | WS_CHILD | WS_VISIBLE | WS_CLIPCHILDREN | WS_CLIPSIBLINGS;

  int bar_x, bar_y, bar_width, bar_height;
  get_bar_placement(bar_x, bar_y, bar_width, bar_height);

  int text_width = text_size.cx + 4;
  int text_height = text_size.cy + 2;
  int text_x = (_win_width - text_width) / 2;
  int text_y = bar_y - text_height - 2;

  _text_label = CreateWindowEx(0, "STATIC", text, window_style,
                               text_x, text_y, text_width, text_height,
                               _hwnd, NULL, application, 0);
  ShowWindow(_text_label, SW_SHOWNORMAL);
}

////////////////////////////////////////////////////////////////////
//     Function: P3DWinSplashWindow::update_image
//       Access: Private
//  Description: Loads the image from the named file (if it has
//               changed), converts to to BITMAP form, and stores it
//               in _bitmap.  Runs only in the sub-thread.
////////////////////////////////////////////////////////////////////
void P3DWinSplashWindow::
update_image(WinImageData &image) {
  if (!image._filename_changed) {
    // No changes.
    return;
  }
  image._filename_changed = false;

  // Clear the old image.
  image.dump_image();

  // Since we'll be displaying a new image, we need to refresh the
  // window.
  InvalidateRect(_hwnd, NULL, TRUE);

  // Go read the image.
  string data;
  if (!read_image_data(image, data, image._filename)) {
    return;
  }

  // Massage the data into Windows' conventions.
  int row_stride = image._width * image._num_channels;
  int new_row_stride = (image._width * 4);

  int new_data_length = new_row_stride * image._height;
  char *new_data = new char[new_data_length];

  if (image._num_channels == 4) {
    // We have to reverse the order of the RGB channels: libjpeg and
    // Windows follow an opposite convention.
    for (int yi = 0; yi < image._height; ++yi) {
      const char *sp = data.data() + yi * row_stride;
      char *dp = new_data + yi * new_row_stride;
      for (int xi = 0; xi < image._width; ++xi) {
        dp[0] = sp[2];
        dp[1] = sp[1];
        dp[2] = sp[0];
        dp[3] = sp[3];
        sp += 4;
        dp += 4;
      }
    }
  } else if (image._num_channels == 3) {
    // We have to reverse the order of the RGB channels: libjpeg and
    // Windows follow an opposite convention.
    for (int yi = 0; yi < image._height; ++yi) {
      const char *sp = data.data() + yi * row_stride;
      char *dp = new_data + yi * new_row_stride;
      for (int xi = 0; xi < image._width; ++xi) {
        dp[0] = sp[2];
        dp[1] = sp[1];
        dp[2] = sp[0];
        dp[3] = (char)0xff;
        sp += 3;
        dp += 4;
      }
    }
  } else if (image._num_channels == 1) {
    // A grayscale image.  Replicate out the channels.
    for (int yi = 0; yi < image._height; ++yi) {
      const char *sp = data.data() + yi * row_stride;
      char *dp = new_data + yi * new_row_stride;
      for (int xi = 0; xi < image._width; ++xi) {
        dp[0] = sp[0];
        dp[1] = sp[0];
        dp[2] = sp[0];
        dp[3] = (char)0xff;
        sp += 1;
        dp += 4;
      }
    }
  }

  // Now load the image.
  BITMAPINFOHEADER bmih;
  bmih.biSize = sizeof(bmih);
  bmih.biWidth = image._width;
  bmih.biHeight = -image._height;
  bmih.biPlanes = 1;
  bmih.biBitCount = 32;
  bmih.biCompression = BI_RGB;
  bmih.biSizeImage = 0;
  bmih.biXPelsPerMeter = 0;
  bmih.biYPelsPerMeter = 0;
  bmih.biClrUsed = 0;
  bmih.biClrImportant = 0;

  BITMAPINFO bmi;
  memcpy(&bmi, &bmih, sizeof(bmih));

  HDC dc = GetDC(_hwnd);
  image._bitmap = CreateDIBitmap(dc, &bmih, CBM_INIT, new_data, &bmi, 0);
  ReleaseDC(_hwnd, dc);

  delete[] new_data;

  nout << "Loaded image: " << image._filename << "\n";
}

////////////////////////////////////////////////////////////////////
//     Function: P3DWinSplashWindow::close_window
//       Access: Private
//  Description: Closes the window created above.  This call is
//               actually made in the main thread.
////////////////////////////////////////////////////////////////////
void P3DWinSplashWindow::
close_window() {
  if (_hwnd != NULL) {
    ShowWindow(_hwnd, SW_HIDE);
    CloseWindow(_hwnd);
    _hwnd = NULL;
  }

  _background_image.dump_image();
  _button_ready_image.dump_image();
  _button_rollover_image.dump_image();
  _button_click_image.dump_image();
}

////////////////////////////////////////////////////////////////////
//     Function: P3DWinSplashWindow::paint_window
//       Access: Private
//  Description: Paints the contents of the window into the indicated
//               DC.
////////////////////////////////////////////////////////////////////
void P3DWinSplashWindow::
paint_window(HDC dc) {
  RECT rect;
  GetClientRect(_hwnd, &rect);

  int width = rect.right - rect.left;
  int height = rect.bottom - rect.top;
  if (width != _win_width || height != _win_height) {
    _win_width = width;
    _win_height = height;
    set_button_range(_button_ready_image);
  }

  // Double-buffer with an offscreen bitmap first.
  HDC bdc = CreateCompatibleDC(dc);
  HBITMAP buffer = CreateCompatibleBitmap(dc, _win_width, _win_height);
  SelectObject(bdc, buffer);

  // Start by painting the background color.
  FillRect(bdc, &rect, WHITE_BRUSH);

  // Then paint the background image on top of that.
  paint_image(bdc, _background_image);

  // And then, paint the button, if any, on top of *that*.
  switch (_drawn_bstate) {
  case BS_hidden:
    break;
  case BS_ready:
    paint_image(bdc, _button_ready_image);
    break;
  case BS_rollover:
    if (!paint_image(bdc, _button_rollover_image)) {
      paint_image(bdc, _button_ready_image);
    }
    break;
  case BS_click:
    if (!paint_image(bdc, _button_click_image)) {
      paint_image(bdc, _button_ready_image);
    }
    break;
  }

  // Now blit the buffer to the window.
  BitBlt(dc, 0, 0, _win_width, _win_height, bdc, 0, 0, SRCCOPY);

  DeleteObject(bdc);
  DeleteObject(buffer);
}
  
////////////////////////////////////////////////////////////////////
//     Function: P3DWinSplashWindow::paint_image
//       Access: Private
//  Description: Draws the indicated image, centered within the
//               window.  Returns true on success, false if the image
//               is not defined.
////////////////////////////////////////////////////////////////////
bool P3DWinSplashWindow::
paint_image(HDC dc, const WinImageData &image) {
  if (image._bitmap == NULL) {
    return false;
  }

  // Paint the background splash image.
  HDC mem_dc = CreateCompatibleDC(dc);
  SelectObject(mem_dc, image._bitmap);
  
  // Determine the relative size of bitmap and window.
  int win_cx = _win_width / 2;
  int win_cy = _win_height / 2;

  BLENDFUNCTION bf;
  bf.BlendOp = AC_SRC_OVER;
  bf.BlendFlags = 0;
  bf.SourceConstantAlpha = 0xff;
  bf.AlphaFormat = AC_SRC_ALPHA;
  
  if (image._width <= _win_width && image._height <= _win_height) {
    // The bitmap fits within the window; center it.
    
    // This is the top-left corner of the bitmap in window coordinates.
    int p_x = win_cx - image._width / 2;
    int p_y = win_cy - image._height / 2;
    
    AlphaBlend(dc, p_x, p_y, image._width, image._height,
               mem_dc, 0, 0, image._width, image._height,
               bf);
    
  } else {
    // The bitmap is larger than the window; scale it down.
    double x_scale = (double)_win_width / (double)image._width;
    double y_scale = (double)_win_height / (double)image._height;
    double scale = min(x_scale, y_scale);
    int sc_width = (int)(image._width * scale);
    int sc_height = (int)(image._height * scale);
    
    int p_x = win_cx - sc_width / 2;
    int p_y = win_cy - sc_height / 2;

    AlphaBlend(dc, p_x, p_y, sc_width, sc_height,
               mem_dc, 0, 0, image._width, image._height, 
               bf);
  }
  
  SelectObject(mem_dc, NULL);
  DeleteDC(mem_dc);

  return true;
}

////////////////////////////////////////////////////////////////////
//     Function: P3DWinSplashWindow::window_proc
//       Access: Private
//  Description: The windows event-processing handler.
////////////////////////////////////////////////////////////////////
LONG P3DWinSplashWindow::
window_proc(HWND hwnd, UINT msg, WPARAM wparam, LPARAM lparam) {
  switch (msg) {
  case WM_DESTROY:
    PostQuitMessage(0);
    break;

  case WM_SIZE:
    InvalidateRect(hwnd, NULL, FALSE);
    break;

  case WM_ERASEBKGND:
    return true;
    
  case WM_PAINT:
    {
      PAINTSTRUCT ps;
      HDC dc = BeginPaint(hwnd, &ps);
      paint_window(dc);
      EndPaint(hwnd, &ps);
    }
    return true;

  case WM_DRAWITEM:
    // Draw a text label placed within the window.
    {
      DRAWITEMSTRUCT *dis = (DRAWITEMSTRUCT *)lparam;
      FillRect(dis->hDC, &(dis->rcItem), WHITE_BRUSH);

      static const int text_buffer_size = 512;
      char text_buffer[text_buffer_size];
      GetWindowText(dis->hwndItem, text_buffer, text_buffer_size);

      HFONT font = (HFONT)GetStockObject(ANSI_VAR_FONT); 
      SelectObject(dis->hDC, font);
      SetBkColor(dis->hDC, 0x00ffffff);

      DrawText(dis->hDC, text_buffer, -1, &(dis->rcItem), 
               DT_VCENTER | DT_CENTER | DT_SINGLELINE);
    }
    return true;

  case WM_MOUSEMOVE: 
    set_mouse_data(LOWORD(lparam), HIWORD(lparam), _mouse_down);
    break;

  case WM_LBUTTONDOWN:
    SetCapture(hwnd);
    set_mouse_data(_mouse_x, _mouse_y, true);
    break;

  case WM_LBUTTONUP:
    set_mouse_data(_mouse_x, _mouse_y, false);
    ReleaseCapture();
    break;
  };

  return DefWindowProc(hwnd, msg, wparam, lparam);
}

////////////////////////////////////////////////////////////////////
//     Function: P3DWinSplashWindow::st_window_proc
//       Access: Private, Static
//  Description: The windows event-processing handler, static version.
////////////////////////////////////////////////////////////////////
LONG P3DWinSplashWindow::
st_window_proc(HWND hwnd, UINT msg, WPARAM wparam, LPARAM lparam) {
  LONG_PTR self = GetWindowLongPtr(hwnd, GWLP_USERDATA);
  if (self == NULL) {
    // We haven't assigned the pointer yet.
    return DefWindowProc(hwnd, msg, wparam, lparam);
  }

  return ((P3DWinSplashWindow *)self)->window_proc(hwnd, msg, wparam, lparam);
}

////////////////////////////////////////////////////////////////////
//     Function: P3DWinSplashWindow::WinImageData::dump_image
//       Access: Public
//  Description: Frees the previous image data.
////////////////////////////////////////////////////////////////////
void P3DWinSplashWindow::WinImageData::
dump_image() {
  if (_bitmap != NULL) {
    DeleteObject(_bitmap);
    _bitmap = NULL;
  }
}

#endif  // _WIN32
