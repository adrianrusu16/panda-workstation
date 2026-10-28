// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <stdexcept>

namespace panda {
// The generic form permits compile-only null-path tests without a Qt process.
template<class Screen>
constexpr auto checkedScreenDevicePixelRatio(Screen *screen)
    -> decltype(screen->devicePixelRatio())
{
    if (screen == nullptr)
        throw std::runtime_error("offscreen primary screen unavailable");
    return screen->devicePixelRatio();
}
} // namespace panda
