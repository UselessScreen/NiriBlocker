# Niri Compatibility Gaps and Fixes

This audit tracks where enforcement logic assumed Hyprland behavior and how Niri support now behaves.

## Confirmed fixes

1. **Compositor lock-in after startup**
   - **Problem:** once a compositor was cached, the daemon only queried that compositor forever. If Hyprland failed later (or the session switched to Niri), monitoring stayed broken.
   - **Fix:** `CompositorMonitor.get_all_windows()` now re-detects the compositor when the cached one fails and falls back to the other supported compositor.
   - **Files:** `daemon/hyprland_monitor.py`, `tests/test_compositor_monitor.py`

2. **Niri XWayland/window-class fallback**
   - **Problem:** Niri normalization only read `app_id`; windows with `app_id: null` were normalized as empty class names and could bypass app-matching rules.
   - **Fix:** Niri normalization now falls back to `class` and `window_properties.class`/`window_properties.instance`.
   - **Files:** `daemon/hyprland_monitor.py`, `tests/test_compositor_monitor.py`

## Current compatibility gaps (not fully solvable in current implementation)

1. **No compositor event subscriptions (polling only)**
   - Current behavior is interval polling (`monitor_check_job`) rather than event-driven subscriptions.
   - Impact: detection/closure latency up to one polling interval and more IPC traffic.

2. **No workspace-aware enforcement model**
   - Rules are global; they do not distinguish active workspace, focused workspace, or monitor-specific workspaces.
   - Niri workspace metadata is not consumed by policy logic today, so workspace-scoped rules are unsupported.

3. **No stable cross-compositor event schema in daemon**
   - The daemon does not consume compositor event streams, so behavior differences between Hyprland socket events and Niri event streams are not abstracted yet.
   - A shared event layer would be required before supporting event-based policy features consistently.
