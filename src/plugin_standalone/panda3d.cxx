// Filename: panda3d.cxx
// Created by:  drose (03Jun09)
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

#include "panda3d.h"
#include "httpClient.h"
#include "load_plugin.h"
#include "find_root_dir.h"
#include "p3d_plugin_config.h"

#include <sstream>
#ifdef _WIN32
#include <windows.h>
#endif

#ifndef HAVE_GETOPT
  #include "gnu_getopt.h"
#else
  #ifdef HAVE_GETOPT_H
    #include <getopt.h>
  #endif
#endif


////////////////////////////////////////////////////////////////////
//     Function: Panda3D::Constructor
//       Access: Public
//  Description: 
////////////////////////////////////////////////////////////////////
Panda3D::
Panda3D() {
  _root_dir = find_root_dir();
}

////////////////////////////////////////////////////////////////////
//     Function: Panda3D::run
//       Access: Public
//  Description: Starts the program going.  Returns 0 on success,
//               nonzero on failure.
////////////////////////////////////////////////////////////////////
int Panda3D::
run(int argc, char *argv[]) {
  extern char *optarg;
  extern int optind;
  const char *optstr = "u:p:fl:t:s:o:h";

  string root_url = P3D_PLUGIN_DOWNLOAD;
  string this_platform = P3D_PLUGIN_PLATFORM;
  bool force_download = false;

  Filename output_filename;
  P3D_window_type window_type = P3D_WT_toplevel;
  int win_x = 0, win_y = 0;
  int win_width = 0, win_height = 0;

  int flag = getopt(argc, argv, optstr);

  while (flag != EOF) {
    switch (flag) {
    case 'u':
      root_url = optarg;
      if (!root_url.empty() && root_url[root_url.length() - 1] != '/') {
        root_url += '/';
      }
      break;

    case 'p':
      this_platform = optarg;
      break;

    case 'f':
      force_download = true;
      break;

    case 'l':
      output_filename = Filename::from_os_specific(optarg);
      break;

    case 't':
      if (strcmp(optarg, "toplevel") == 0) {
        window_type = P3D_WT_toplevel;
      } else if (strcmp(optarg, "embedded") == 0) {
        window_type = P3D_WT_embedded;
      } else if (strcmp(optarg, "fullscreen") == 0) {
        window_type = P3D_WT_fullscreen;
      } else if (strcmp(optarg, "hidden") == 0) {
        window_type = P3D_WT_hidden;
      } else {
        cerr << "Invalid value for -t: " << optarg << "\n";
        return 1;
      }
      break;

    case 's':
      if (!parse_int_pair(optarg, win_width, win_height)) {
        cerr << "Invalid value for -s: " << optarg << "\n";
        return 1;
      }
      break;

    case 'o':
      if (!parse_int_pair(optarg, win_x, win_y)) {
        cerr << "Invalid value for -o: " << optarg << "\n";
        return 1;
      }
      break;

    case 'h':
    case '?':
    default:
      usage();
      return 1;
    }
    flag = getopt(argc, argv, optstr);
  }

  argc -= (optind-1);
  argv += (optind-1);

  if (argc < 2) {
    usage();
    return 1;
  }

  if (!get_plugin(root_url, this_platform, force_download)) {
    cerr << "Unable to load Panda3D plugin.\n";
    return 1;
  }

  int num_instances = argc - 1;

  P3D_window_handle parent_window;
  if (window_type == P3D_WT_embedded) {
    // The user asked for an embedded window.  Create a toplevel
    // window to be its parent, of the requested size.
    if (win_width == 0 && win_height == 0) {
      win_width = 640;
      win_height = 480;
    }

    make_parent_window(parent_window, win_width, win_height);
    
    // Center the child window(s) within the parent window.
#ifdef _WIN32
    RECT rect;
    GetClientRect(parent_window._hwnd, &rect);

    win_x = (int)(rect.right * 0.1);
    win_y = (int)(rect.bottom * 0.1);
    win_width = (int)(rect.right * 0.8);
    win_height = (int)(rect.bottom * 0.8);
#endif

    // Subdivide the window into num_x_spans * num_y_spans sub-windows.
    int num_y_spans = int(sqrt((double)num_instances));
    int num_x_spans = (num_instances + num_y_spans - 1) / num_y_spans;
    
    int inst_width = win_width / num_x_spans;
    int inst_height = win_height / num_y_spans;

    for (int yi = 0; yi < num_y_spans; ++yi) {
      for (int xi = 0; xi < num_x_spans; ++xi) {
        int i = yi * num_x_spans + xi;
        if (i >= num_instances) {
          continue;
        }

        // Create instance i at window slot (xi, yi).
        int inst_x = win_x + xi * inst_width;
        int inst_y = win_y + yi * inst_height;

        P3D_instance *inst = create_instance
          (argv[i + 1], P3D_WT_embedded, 
           inst_x, inst_y, inst_width, inst_height, parent_window,
           output_filename);
        _instances.insert(inst);
      }
    }

  } else {
    // Not an embedded window.  Create each window with the same parameters.
    for (int i = 0; i < num_instances; ++i) {
      P3D_instance *inst = create_instance
        (argv[i + 1], window_type, 
         win_x, win_y, win_width, win_height, parent_window,
         output_filename);
      _instances.insert(inst);
    }
  }

#ifdef _WIN32
  if (window_type == P3D_WT_embedded) {
    // Wait for new messages from Windows, and new requests from the
    // plugin.
    MSG msg;
    int retval;
    retval = GetMessage(&msg, NULL, 0, 0);
    while (retval != 0 && !_instances.empty()) {
      if (retval == -1) {
        cerr << "Error processing message queue.\n";
        exit(1);
      }
      TranslateMessage(&msg);
      DispatchMessage(&msg);

      // Check for new requests from the Panda3D plugin.
      P3D_instance *inst = P3D_check_request(false);
      while (inst != (P3D_instance *)NULL) {
        P3D_request *request = P3D_instance_get_request(inst);
        if (request != (P3D_request *)NULL) {
          handle_request(request);
        }
        inst = P3D_check_request(false);
      }

      while (!_url_getters.empty() && 
             !PeekMessage(&msg, NULL, 0, 0, PM_NOREMOVE)) {
        // If there are no Windows messages, check the download tasks.
        run_getters();
      }
      retval = GetMessage(&msg, NULL, 0, 0);
    }
    
    cerr << "WM_QUIT\n";
    // WM_QUIT has been received.  Terminate all instances, and fall
    // through.
    while (!_instances.empty()) {
      P3D_instance *inst = *(_instances.begin());
      delete_instance(inst);
    }

  } else {
    // Not an embedded window, so we don't have our own window to
    // generate Windows events.  Instead, just wait for requests.
    while (!_instances.empty()) {
      P3D_instance *inst = P3D_check_request(false);
      if (inst != (P3D_instance *)NULL) {
        P3D_request *request = P3D_instance_get_request(inst);
        if (request != (P3D_request *)NULL) {
          handle_request(request);
        }
      }
      run_getters();
    }
  }
    
#endif

  // Now wait while we process pending requests.
  while (!_instances.empty()) {
    P3D_instance *inst = P3D_check_request(false);
    if (inst != (P3D_instance *)NULL) {
      P3D_request *request = P3D_instance_get_request(inst);
      if (request != (P3D_request *)NULL) {
        handle_request(request);
      }
    }
    run_getters();
  }

  // All instances have finished; we can exit.
  cerr << "clean exit\n";
  unload_plugin();
  return 0;
}

////////////////////////////////////////////////////////////////////
//     Function: Panda3D::get_plugin
//       Access: Private
//  Description: Downloads the contents.xml file from the named URL
//               and attempts to use it to load the core API.  Returns
//               true on success, false on failure.
////////////////////////////////////////////////////////////////////
bool Panda3D::
get_plugin(const string &root_url, const string &this_platform, bool force_download) {
  // First, look for the existing contents.xml file.
  Filename contents = Filename(Filename::from_os_specific(_root_dir), "contents.xml");
  if (!force_download && read_contents_file(contents, root_url, this_platform)) {
    // Got the file, and it's good.
    return true;
  }

  // Couldn't read it, so go get it.
  string url = root_url;
  if (url.size() > 0 && url[url.size()-1] != '/') {
    url += "/";
  }
  url += "contents.xml";
  cerr << "Getting URL " << url << "\n";
  
  HTTPClient *http = HTTPClient::get_global_ptr();
  PT(HTTPChannel) channel = http->get_document(url);
  Ramfile rf;
  if (!channel->download_to_file(contents)) {
    cerr << "Unable to download " << url << "\n";
    return false;
  }
  
  return read_contents_file(contents, root_url, this_platform);
}

////////////////////////////////////////////////////////////////////
//     Function: Panda3D::read_contents_file
//       Access: Private
//  Description: Attempts to open and read the contents.xml file on
//               disk, and uses that data to load the plugin, if
//               possible.  Returns true on success, false on failure.
////////////////////////////////////////////////////////////////////
bool Panda3D::
read_contents_file(Filename contents, const string &root_url, 
                   const string &this_platform) {
  ifstream in;
  contents.set_text();
  if (!contents.open_read(in)) {
    cerr << "Couldn't read " << contents.to_os_specific() << "\n";
    return false;
  }

  TiXmlDocument doc;
  in >> doc;

  TiXmlElement *xcontents = doc.FirstChildElement("contents");
  if (xcontents != NULL) {
    TiXmlElement *xpackage = xcontents->FirstChildElement("package");
    while (xpackage != NULL) {
      const char *name = xpackage->Attribute("name");
      if (name != NULL && strcmp(name, "coreapi") == 0) {
        const char *xplatform = xpackage->Attribute("platform");
        if (xplatform != NULL && strcmp(xplatform, this_platform.c_str()) == 0) {
          return get_core_api(root_url, xpackage);
        }
      }
      
      xpackage = xpackage->NextSiblingElement("package");
    }
  }

  // Couldn't find the coreapi package description.
  cerr << "No coreapi package defined in contents file for "
       << this_platform << "\n";
  return false;
}


////////////////////////////////////////////////////////////////////
//     Function: Panda3D::get_core_api
//       Access: Private
//  Description: Checks the core API DLL file against the
//               specification in the contents file, and downloads it
//               if necessary.
////////////////////////////////////////////////////////////////////
bool Panda3D::
get_core_api(const string &root_url, TiXmlElement *xpackage) {
  _core_api_dll.load_xml(xpackage);

  if (!_core_api_dll.quick_verify(_root_dir)) {
    // The DLL file needs to be downloaded.  Go get it.
    string url = root_url;
    url += _core_api_dll.get_filename();
    
    Filename pathname = Filename::from_os_specific(_core_api_dll.get_pathname(_root_dir));
    HTTPClient *http = HTTPClient::get_global_ptr();
    PT(HTTPChannel) channel = http->get_document(url);
    if (!channel->download_to_file(pathname)) {
      cerr << "Unable to download " << url << "\n";
      return false;
    }

    if (!_core_api_dll.quick_verify(_root_dir)) {
      cerr << "Mismatched download for " << url << "\n";
      return false;
    }
  }

  // Now we've got the DLL.  Load it.
  string pathname = _core_api_dll.get_pathname(_root_dir);

#ifdef P3D_PLUGIN_P3D_PLUGIN
  // This is a convenience macro for development.  If defined and
  // nonempty, it indicates the name of the plugin DLL that we will
  // actually run, even after downloading a possibly different
  // (presumably older) version.  Its purpose is to simplify iteration
  // on the plugin DLL.
  string override_filename = P3D_PLUGIN_P3D_PLUGIN;
  if (!override_filename.empty()) {
    pathname = override_filename;
  }
#endif  // P3D_PLUGIN_P3D_PLUGIN

  if (!load_plugin(pathname)) {
    cerr << "Unable to launch core API in " << pathname << "\n" << flush;
    return false;
  }

  // Successfully loaded.
  return true;
}

////////////////////////////////////////////////////////////////////
//     Function: Panda3D::run_getters
//       Access: Private
//  Description: Polls all of the active URL requests.
////////////////////////////////////////////////////////////////////
void Panda3D::
run_getters() {
  URLGetters::iterator gi;
  gi = _url_getters.begin();
  while (gi != _url_getters.end()) {
    URLGetter *getter = (*gi);
    if (getter->run()) {
      // This URLGetter is still working.  Leave it.
      ++gi;
    } else {
      // This URLGetter is done.  Remove it and delete it.
      URLGetters::iterator dgi = gi;
      ++gi;
      _url_getters.erase(dgi);
      delete getter;
    }
  }
}

////////////////////////////////////////////////////////////////////
//     Function: Panda3D::handle_request
//       Access: Private
//  Description: Handles a single request received via the plugin API
//               from a p3d instance.
////////////////////////////////////////////////////////////////////
void Panda3D::
handle_request(P3D_request *request) {
  bool handled = false;

  switch (request->_request_type) {
  case P3D_RT_stop:
    cerr << "Got P3D_RT_stop\n";
    delete_instance(request->_instance);
#ifdef _WIN32
    // Post a silly message to spin the event loop.
    PostMessage(NULL, WM_USER, 0, 0);
#endif
    handled = true;
    break;

  case P3D_RT_get_url:
    cerr << "Got P3D_RT_get_url: " << request->_request._get_url._url
         << "\n";
    {
      int unique_id = request->_request._get_url._unique_id;
      const string &url = request->_request._get_url._url;
      URLGetter *getter = new URLGetter
        (request->_instance, unique_id, URLSpec(url), "");
      _url_getters.insert(getter);
      handled = true;
    }
    break;

  case P3D_RT_post_url:
    cerr << "Got P3D_RT_post_url: " << request->_request._post_url._url 
         << "\n";
    {
      int unique_id = request->_request._post_url._unique_id;
      const string &url = request->_request._post_url._url;
      string post_data(request->_request._post_url._post_data, 
                       request->_request._post_url._post_data_size);
      URLGetter *getter = new URLGetter
        (request->_instance, unique_id, URLSpec(url), post_data);
      _url_getters.insert(getter);
      handled = true;
    }
    break;

  case P3D_RT_notify:
    cerr << "Got P3D_RT_notify: " << request->_request._notify._message
         << "\n";
    // Ignore notifications.
    break;

  default:
    break;
  };

  P3D_request_finish(request, handled);
}

#ifdef _WIN32
LONG WINAPI
window_proc(HWND hwnd, UINT msg, WPARAM wparam, LPARAM lparam) {
  switch (msg) {
  case WM_DESTROY:
    PostQuitMessage(0);
    break;
  };

  return DefWindowProc(hwnd, msg, wparam, lparam);
}

////////////////////////////////////////////////////////////////////
//     Function: Panda3D::make_parent_window
//       Access: Private
//  Description: Creates a toplevel window to contain the embedded
//               instances.  Windows implementation.
////////////////////////////////////////////////////////////////////
void Panda3D::
make_parent_window(P3D_window_handle &parent_window, 
                   int win_width, int win_height) {
  WNDCLASS wc;

  HINSTANCE application = GetModuleHandle(NULL);
  ZeroMemory(&wc, sizeof(WNDCLASS));
  wc.lpfnWndProc = window_proc;
  wc.hInstance = application;
  wc.hbrBackground = (HBRUSH)GetStockObject(WHITE_BRUSH);
  wc.lpszClassName = "panda3d";

  if (!RegisterClass(&wc)) {
    cerr << "Could not register window class!\n";
    exit(1);
  }

  DWORD window_style = 
    WS_POPUP | WS_CLIPCHILDREN | WS_CLIPSIBLINGS |
    WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX |
    WS_SIZEBOX | WS_MAXIMIZEBOX;

  HWND toplevel_window = 
    CreateWindow("panda3d", "Panda3D", window_style,
                 CW_USEDEFAULT, CW_USEDEFAULT, win_width, win_height,
                 NULL, NULL, application, 0);
  if (!toplevel_window) {
    cerr << "Could not create toplevel window!\n";
    exit(1);
  }

  ShowWindow(toplevel_window, SW_SHOWNORMAL);

  parent_window._hwnd = toplevel_window;
}

#else

////////////////////////////////////////////////////////////////////
//     Function: Panda3D::make_parent_window
//       Access: Private
//  Description: Creates a toplevel window to contain the embedded
//               instances.
////////////////////////////////////////////////////////////////////
void Panda3D::
make_parent_window(P3D_window_handle &parent_window, 
                   int win_width, int win_height) {
  // TODO.
  assert(false);
}

#endif

////////////////////////////////////////////////////////////////////
//     Function: Panda3D::create_instance
//       Access: Private
//  Description: Uses the plugin API to create a new P3D instance to
//               play a particular .p3d file.
////////////////////////////////////////////////////////////////////
P3D_instance *Panda3D::
create_instance(const string &arg, P3D_window_type window_type,
                int win_x, int win_y, int win_width, int win_height,
                P3D_window_handle parent_window,
                const Filename &output_filename) {

  string os_output_filename = output_filename.to_os_specific();
  P3D_token tokens[] = {
    { "output_filename", os_output_filename.c_str() },
    { "src", arg.c_str() },
  };
  int num_tokens = sizeof(tokens) / sizeof(P3D_token);

  // If the supplied parameter name is a real file, pass it in on the
  // parameter list.  Otherwise, assume it's a URL and let the plugin
  // download it.
  Filename p3d_filename = Filename::from_os_specific(arg);
  string os_p3d_filename;
  if (p3d_filename.exists()) {
    p3d_filename.make_absolute();
    os_p3d_filename = p3d_filename.to_os_specific();
  } 

  P3D_instance *inst = P3D_new_instance(NULL, NULL);

  if (inst != NULL) {
    P3D_instance_setup_window
      (inst, window_type, win_x, win_y, win_width, win_height, parent_window);
    P3D_instance_start(inst, os_p3d_filename.c_str(), tokens, num_tokens);
  }

  return inst;
}

////////////////////////////////////////////////////////////////////
//     Function: Panda3D::delete_instance
//       Access: Private
//  Description: Deletes the indicated instance and removes it from
//               the internal structures.
////////////////////////////////////////////////////////////////////
void Panda3D::
delete_instance(P3D_instance *inst) {
  P3D_instance_finish(inst);
  _instances.erase(inst);

  // Make sure we also terminate any pending URLGetters associated
  // with this instance.
  URLGetters::iterator gi;
  gi = _url_getters.begin();
  while (gi != _url_getters.end()) {
    URLGetter *getter = (*gi);
    if (getter->get_instance() == inst) {
      URLGetters::iterator dgi = gi;
      ++gi;
      _url_getters.erase(dgi);
      delete getter;
    }
  }
}

////////////////////////////////////////////////////////////////////
//     Function: Panda3D::usage
//       Access: Private
//  Description: Reports the available command-line options.
////////////////////////////////////////////////////////////////////
void Panda3D::
usage() {
  cerr
    << "\nUsage:\n"
    << "   panda3d [opts] file.p3d [file_b.p3d file_c.p3d ...]\n\n"
  
    << "This program is used to execute a Panda3D application bundle stored\n"
    << "in a .p3d file.  Normally you only run one p3d bundle at a time,\n"
    << "but it is possible to run multiple bundles simultaneously.\n\n"

    << "Options:\n\n"

    << "  -l output.log\n"
    << "    Specify the name of the file to receive the log output of the\n"
    << "    plugin process(es).  The default is to send this output to the\n"
    << "    console.\n\n"

    << "  -t [toplevel|embedded|fullscreen|hidden]\n"
    << "    Specify the type of graphic window to create.  If you specify\n"
    << "    \"embedded\", a new window is created to be the parent.\n\n"

    << "  -s width,height\n"
    << "    Specify the size of the graphic window.\n\n"

    << "  -o x,y\n"
    << "    Specify the position (origin) of the graphic window on the\n"
    << "    screen, or on the parent window.\n\n"

    << "  -f\n"
    << "    Force a HTTP contact to the Panda3D download server, to check\n"
    << "    if a new version is available.  Normally, this is done only\n"
    << "    if contents.xml cannot be read.\n\n"

    << "  -u url\n"
    << "    Specify the URL of the Panda3D download server.  The default is\n"
    << "    " << P3D_PLUGIN_DOWNLOAD << "\n\n"

    << "  -p platform\n"
    << "    Specify the platform to masquerade as.  The default is "
    << P3D_PLUGIN_PLATFORM << "\n\n";
}

////////////////////////////////////////////////////////////////////
//     Function: Panda3D::parse_int_pair
//       Access: Private
//  Description: Parses a string into an x,y pair of integers.
//               Returns true on success, false on failure.
////////////////////////////////////////////////////////////////////
bool Panda3D::
parse_int_pair(char *arg, int &x, int &y) {
  char *endptr;
  x = strtol(arg, &endptr, 10);
  if (*endptr == ',') {
    y = strtol(endptr + 1, &endptr, 10);
    if (*endptr == '\0') {
      return true;
    }
  }

  // Some parse error on the string.
  return false;
}

////////////////////////////////////////////////////////////////////
//     Function: Panda3D::URLGetter::Constructor
//       Access: Public
//  Description: 
////////////////////////////////////////////////////////////////////
Panda3D::URLGetter::
URLGetter(P3D_instance *instance, int unique_id,
          const URLSpec &url, const string &post_data) :
  _instance(instance),
  _unique_id(unique_id),
  _url(url),
  _post_data(post_data)
{
  HTTPClient *http = HTTPClient::get_global_ptr();

  cerr << "Getting URL " << _url << "\n";

  _channel = http->make_channel(false);
  if (_post_data.empty()) {
    _channel->begin_get_document(_url);
  } else {
    _channel->begin_post_form(_url, _post_data);
  }

  _channel->download_to_ram(&_rf);
  _bytes_sent = 0;
}

////////////////////////////////////////////////////////////////////
//     Function: Panda3D::URLGetter::run
//       Access: Public
//  Description: Polls the URLGetter for new results.  Returns true if
//               the URL request is still in progress and run() should
//               be called again later, or false if the URL request
//               has been completed and run() should not be called
//               again.
////////////////////////////////////////////////////////////////////
bool Panda3D::URLGetter::
run() {
  if (_channel->run() || _rf.get_data_size() != 0) {
    if (_rf.get_data_size() != 0) {
      // Got some new data.
      bool download_ok = P3D_instance_feed_url_stream
        (_instance, _unique_id, P3D_RC_in_progress,
         _channel->get_status_code(),
         _channel->get_file_size(),
         (const unsigned char *)_rf.get_data().data(), _rf.get_data_size());
      _bytes_sent += _rf.get_data_size();
      _rf.clear();

      if (!download_ok) {
        // The plugin doesn't care any more.  Interrupt the download.
        cerr << "Download interrupted: " << _url 
             << ", after " << _bytes_sent << " of " << _channel->get_file_size()
             << " bytes.\n";
        return false;
      }
    }

    // Still more to come; call this method again later.
    return true;
  }

  // All done.
  P3D_result_code status = P3D_RC_done;
  if (!_channel->is_valid()) {
    if (_channel->get_status_code() != 0) {
      status = P3D_RC_http_error;
    } else {
      status = P3D_RC_generic_error;
    }
    cerr << "Error getting URL " << _url << "\n";
  } else {
    cerr << "Done getting URL " << _url << ", got " << _bytes_sent << " bytes\n";
  }

  P3D_instance_feed_url_stream
    (_instance, _unique_id, status,
     _channel->get_status_code(),
     _bytes_sent, NULL, 0);
  return false;
}


int
main(int argc, char *argv[]) {
  Panda3D program;
  return program.run(argc, argv);
}
