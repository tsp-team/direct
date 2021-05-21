/**
 * PANDA 3D SOFTWARE
 * Copyright (c) Carnegie Mellon University.  All rights reserved.
 *
 * All use of this software is subject to the terms of the revised BSD
 * license.  You should have received a copy of this license along
 * with this source code in a file named "LICENSE."
 *
 * @file interpolatedVariable.cxx
 * @author brian
 * @date 2021-05-03
 */

#include "interpolatedVariable.h"

InterpolationContext *InterpolationContext::_head = nullptr;
bool InterpolationContext::_allow_extrapolation = false;
double InterpolationContext::_last_timestamp = 0;