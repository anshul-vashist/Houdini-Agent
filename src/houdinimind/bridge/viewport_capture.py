# ==============================================================================
# Creator: Anshul Vashist
# Email: vashistanshul.7@gmail.com
# LinkedIn: https://www.linkedin.com/in/av-0001/
# ==============================================================================
from __future__ import annotations

"""
HoudiniMind — Viewport & Network Editor Screenshot Capture
Grabs live PNG screenshots of Houdini panes for vision-enabled LLM context.

Capture strategy (tried in order):
  1. hou.ui.paneTabOfType → find matching Qt widget by walking the widget tree
  2. Grab the full Houdini main window as a fallback
"""

import base64
import os

try:
    import hou
    from PySide6 import QtCore, QtGui, QtWidgets

    HOU_AVAILABLE = True
except ImportError:
    HOU_AVAILABLE = False
    QtWidgets = None
    QtCore = None
    QtGui = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _pixmap_to_b64(pixmap) -> str | None:
    """Convert a QPixmap → base64-encoded PNG string."""
    try:
        buf = QtCore.QBuffer()
        buf.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
        pixmap.save(buf, "PNG")
        raw = bytes(buf.data())
        buf.close()
        if not raw:
            return None
        return base64.b64encode(raw).decode("utf-8")
    except Exception as e:
        print(f"[HoudiniMind Vision] pixmap_to_b64 error: {e}")
        return None


def _extract_screen_rect(bounds) -> tuple | None:
    """
    Normalize Houdini pane bounds into a plain (left, top, right, bottom) tuple.

    Depending on the Houdini version / API surface, screenBounds() may return a
    tuple-like object or a BoundingRect instance with accessor methods.
    """
    if bounds is None:
        return None

    try:
        values = tuple(bounds)
        if len(values) == 4:
            return tuple(int(v) for v in values)
    except Exception:
        pass

    try:
        as_tuple = bounds.asTuple()
        if len(as_tuple) == 4:
            return tuple(int(v) for v in as_tuple)
    except Exception:
        pass

    def _read_value(obj, *names):
        for name in names:
            if not hasattr(obj, name):
                continue
            value = getattr(obj, name)
            try:
                value = value() if callable(value) else value
            except TypeError:
                continue
            if value is not None:
                return value
        return None

    left = _read_value(bounds, "left", "x1", "xmin", "minX", "minx")
    top = _read_value(bounds, "top", "y1", "ymin", "minY", "miny")
    right = _read_value(bounds, "right", "x2", "xmax", "maxX", "maxx")
    bottom = _read_value(bounds, "bottom", "y2", "ymax", "maxY", "maxy")
    if None not in (left, top, right, bottom):
        return tuple(int(v) for v in (left, top, right, bottom))

    return None


def _find_houdini_main_window() -> QtWidgets.QWidget | None:
    """Return the top-level Houdini main window widget."""
    app = QtWidgets.QApplication.instance()
    if app is None:
        return None

    # Prefer explicit Houdini main window helpers when available.
    try:
        import hou.qt as hqt

        win = hqt.mainWindow()
        if win:
            return win
    except Exception:
        pass

    try:
        active = app.activeWindow()
        if active and active.isVisible():
            return active
    except Exception:
        pass

    # Prefer hou.qt helper if available (H19+)
    try:
        import hou.qt as hqt

        win = hqt.mainWindow()
        if win and win.isVisible():
            return win
    except Exception:
        pass

    # Fallback: walk top-level widgets, score Houdini-looking windows first
    def _score(widget):
        try:
            title = (widget.windowTitle() or "").lower()
        except Exception:
            title = ""
        try:
            obj = (widget.objectName() or "").lower()
        except Exception:
            obj = ""
        score = 0
        if widget.isVisible():
            score += 10
        if widget.width() > 600 and widget.height() > 400:
            score += 5
        if "houdini" in title or "houdini" in obj:
            score += 20
        if "scene" in title or "viewer" in title or "scene" in obj or "viewer" in obj:
            score += 8
        return score

    candidates = [w for w in app.topLevelWidgets() if w.width() > 300 and w.height() > 200]
    if not candidates:
        return None
    return sorted(candidates, key=_score, reverse=True)[0]


def _find_scene_viewer_widget() -> QtWidgets.QWidget | None:
    """Best-effort lookup for the visible Scene Viewer widget.

    Uses the same positive/negative keyword filtering as
    ``_is_scene_viewer_widget`` so the HoudiniMind chat panel and
    other non-viewport panes are never returned.
    """
    app = QtWidgets.QApplication.instance()
    if app is None:
        return None

    candidates = []
    for w in app.allWidgets():
        try:
            if not w.isVisible():
                continue
            # Skip tiny widgets (toolbar icons, buttons, etc.)
            if w.width() < 200 or w.height() < 200:
                continue
            if _is_scene_viewer_widget(w):
                candidates.append(w)
        except Exception:
            continue
    if not candidates:
        return None
    return sorted(candidates, key=lambda w: w.width() * w.height(), reverse=True)[0]


def _is_scene_viewer_widget(widget: QtWidgets.QWidget) -> bool:
    """Return True only for widgets that identify as a Scene Viewer/viewport.

    The negative-keyword list is deliberately broad so the HoudiniMind Python
    Panel (and similar chat/agent UIs) can never be mistaken for the 3-D
    viewport, even if their parent pane-tab carries a 'viewport' token.
    """
    try:
        cls = widget.metaObject().className().lower()
    except Exception:
        cls = ""
    try:
        obj = (widget.objectName() or "").lower()
    except Exception:
        obj = ""
    try:
        title = (widget.windowTitle() or "").lower()
    except Exception:
        title = ""
    text = " ".join([cls, obj, title])
    negative = (
        "chat",
        "message",
        "conversation",
        "houdinimind",
        "panel",
        "pythonpanel",
        "python_panel",
        "agent",
        "pyside",
        "input",
        "scroll",
        "button",
        "label",
        "settings",
        "composer",
        "chat_lane",
        "tool_card",
        "bubble",
    )
    positive = ("sceneviewer", "scene viewer", "viewport", "glview", "glviewport")
    return any(token in text for token in positive) and not any(token in text for token in negative)


def _widget_for_pane(pane_tab) -> QtWidgets.QWidget | None:
    """
    Try to find the Qt widget that owns a Houdini PaneTab.
    Works by matching the pane's screen rectangle against QWidget geometries.
    """
    try:
        # H20+ exposes paneTab.qtParentWidget()
        if hasattr(pane_tab, "qtParentWidget"):
            w = pane_tab.qtParentWidget()
            if w is not None and _is_scene_viewer_widget(w):
                return w
    except Exception:
        pass

    try:
        pane_type_name = pane_tab.type().name().lower()
    except Exception:
        pane_type_name = ""

    if pane_type_name == "sceneviewer":
        widget = _find_scene_viewer_widget()
        if widget is not None:
            return widget

    # Geometry-matching fallback: get pane global position from hou
    try:
        bounds = _extract_screen_rect(pane_tab.screenBounds())
        if not bounds:
            return None
        target_rect = QtCore.QRect(
            bounds[0], bounds[1], bounds[2] - bounds[0], bounds[3] - bounds[1]
        )

        app = QtWidgets.QApplication.instance()
        for w in app.allWidgets():
            if not w.isVisible():
                continue
            gr = w.geometry()
            gp = w.mapToGlobal(QtCore.QPoint(0, 0))
            global_rect = QtCore.QRect(gp.x(), gp.y(), gr.width(), gr.height())
            if global_rect == target_rect:
                return w
    except Exception:
        pass

    return None


def _grab_widget(widget: QtWidgets.QWidget, scale: float = 1.0) -> str | None:
    """Grab a widget, optionally downscale, return base64 PNG."""
    try:
        pixmap = widget.grab()
        if pixmap is None or pixmap.isNull():
            pixmap = QtGui.QPixmap(widget.size())
            pixmap.fill(QtCore.Qt.GlobalColor.transparent)
            try:
                widget.render(pixmap)
            except Exception:
                pass
        if scale != 1.0:
            new_w = int(pixmap.width() * scale)
            new_h = int(pixmap.height() * scale)
            pixmap = pixmap.scaled(
                new_w,
                new_h,
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation,
            )
        return _pixmap_to_b64(pixmap)
    except Exception as e:
        print(f"[HoudiniMind Vision] grab_widget error: {e}")
        return None


def _grab_screen_rect(x: int, y: int, w: int, h: int) -> str | None:
    """Grab an absolute screen rectangle using QScreen."""
    try:
        app = QtWidgets.QApplication.instance()
        screen = app.primaryScreen() if app else None
        if screen is None and app is not None:
            center = QtCore.QPoint(int(x + w / 2), int(y + h / 2))
            screen = app.screenAt(center)
        if screen is None:
            return None
        pixmap = screen.grabWindow(0, x, y, w, h)
        if pixmap is None or pixmap.isNull():
            return None
        return _pixmap_to_b64(pixmap)
    except Exception as e:
        print(f"[HoudiniMind Vision] grab_screen_rect error: {e}")
        return None


def _flipbook_viewport(viewer, scale: float = 0.75) -> str | None:
    """
    Capture the Scene Viewer via Houdini flipbook.
    This is the most reliable path for actual 3D viewport contents.
    """
    try:
        # 1. Force the viewer to be the current tab BEFORE we ask for the viewport.
        # If it's not current, curViewport() often returns None.
        for method_name in ("setIsCurrentTab", "setCurrent", "setFocus", "raise_"):
            try:
                method = getattr(viewer, method_name, None)
                if callable(method):
                    try:
                        method()
                    except TypeError:
                        method(True)
            except Exception:
                pass

        # Give Houdini a moment to switch tabs and redraw
        try:
            import hou

            hou.ui.triggerUpdate()
            import time as _time

            _time.sleep(0.15)  # increased from 0.1 for reliable redraw
        except Exception:
            pass

        viewport = viewer.curViewport()
        if viewport is None:
            raise RuntimeError(
                "viewer.curViewport() returned None. The viewer might be fully obscured or invalid."
            )

        flip_settings = viewer.flipbookSettings().stash()
        import tempfile

        tmp_path = os.path.join(tempfile.gettempdir(), "hmind_viewport_capture.png").replace(
            "\\", "/"
        )
        flip_settings.output(tmp_path)
        flip_settings.frameRange((hou.frame(), hou.frame()))
        # Pin the flipbook resolution to the viewport's pixel size so the
        # framebuffer aspect ratio matches what frameAll() framed against.
        # If we let Houdini pick a default the resulting image often has a
        # different aspect than the viewport, which crops top/bottom of the
        # geometry even after a clean frameAll.
        try:
            vp_size = viewport.size()  # (x, y, width, height) on most builds
            if vp_size and len(vp_size) >= 4:
                w = max(int(vp_size[2]), 64)
                h = max(int(vp_size[3]), 64)
                if hasattr(flip_settings, "resolution"):
                    flip_settings.resolution((w, h))
                if hasattr(flip_settings, "useResolution"):
                    flip_settings.useResolution(True)
        except Exception:
            pass
        if hasattr(flip_settings, "outputToMPlay"):
            flip_settings.outputToMPlay(False)

        viewer.flipbook(viewport, flip_settings)

        # Poll briefly — flipbook sometimes returns before the file is flushed.
        import time as _time

        for _ in range(30):  # Wait up to 3 seconds
            if os.path.exists(tmp_path):
                break
            _time.sleep(0.1)
        else:
            raise RuntimeError(
                f"Houdini failed to write flipbook file to {tmp_path} after 3 seconds."
            )

        pixmap = QtGui.QPixmap(tmp_path)
        if pixmap.isNull():
            raise RuntimeError(f"QPixmap failed to load valid image data from {tmp_path}")
        if scale != 1.0:
            new_w = int(pixmap.width() * scale)
            new_h = int(pixmap.height() * scale)
            pixmap = pixmap.scaled(
                new_w,
                new_h,
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation,
            )

        b64_str = _pixmap_to_b64(pixmap)
        try:
            os.remove(tmp_path)
        except Exception:
            pass
        return b64_str
    except Exception as e:
        raise RuntimeError(f"Flipbook failed: {e!s}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def capture_network_editor(scale: float = 0.75, node_path: str | None = None) -> str | None:
    """
    Capture the Network Editor pane, optionally framing a specific node.
    Returns base64 PNG string, or None if unavailable.
    """
    if not HOU_AVAILABLE:
        return None
    try:
        pane = hou.ui.paneTabOfType(hou.paneTabType.NetworkEditor)
        if pane is None:
            return None

        # Framing logic: if node_path is provided, focus the editor there
        if node_path:
            node = hou.node(node_path)
            if node:
                parent = node.parent()
                if parent:
                    pane.setPwd(parent)
                node.setSelected(True, clear_all_selected=True)
                pane.homeToSelection()

        widget = _widget_for_pane(pane)
        if widget:
            return _grab_widget(widget, scale=scale)

        # Screen-rect fallback
        bounds = _extract_screen_rect(pane.screenBounds())
        if not bounds:
            return None
        return _grab_screen_rect(bounds[0], bounds[1], bounds[2] - bounds[0], bounds[3] - bounds[1])
    except Exception as e:
        print(f"[HoudiniMind Vision] capture_network_editor error: {e}")
        return None


def _frame_viewport(viewer, padding: float = 0.12) -> None:
    """
    Frame all objects in the viewport by simulating a human selecting the
    display nodes and calling frameSelected().
    """
    try:
        import hou

        viewport = viewer.curViewport()
        if viewport is None:
            return

        # Find displayed SOPs to select them for framing
        displayed_nodes = []
        for obj in hou.node("/obj").children():
            if obj.isDisplayFlagSet():
                disp = obj.displayNode()
                if disp:
                    displayed_nodes.append(disp)
                else:
                    displayed_nodes.append(obj)

        if displayed_nodes:
            hou.clearAllSelected()
            for node in displayed_nodes:
                node.setSelected(True, clear_all_selected=False)

        hou.ui.triggerUpdate()

        try:
            viewport.frameSelected()
        except Exception:
            viewport.frameAll()

        try:
            cam = viewport.defaultCamera()
            # Ortho: widen the ortho frustum to add margin.
            try:
                ortho_w = cam.orthoWidth()
                if ortho_w and ortho_w > 0:
                    cam.setOrthoWidth(ortho_w * (1.0 + padding))
            except Exception:
                pass
            # Perspective: dolly the camera away from its pivot.
            try:
                pivot = cam.pivot()
                trans = cam.translation()
                offset = trans - pivot
                cam.setTranslation(pivot + offset * (1.0 + padding))
            except Exception:
                pass
            viewport.setDefaultCamera(cam)
        except Exception:
            pass

        # Force a UI repaint so the new framing is visible in the grab
        try:
            hou.ui.triggerUpdate()
            import time as _t

            _t.sleep(0.15)
        except Exception:
            pass
    except Exception as e:
        print(f"[HoudiniMind Vision] frameSelected error (non-fatal): {e}")


def capture_viewport(scale: float = 0.75) -> str | None:
    """
    Capture the 3-D Scene Viewer (viewport) pane.

    Validation-grade path uses Houdini flipbook first. Widget/screen grabs are
    fallbacks only because they can accidentally capture surrounding UI panels.

    Returns base64 PNG string, or None if unavailable.
    """
    if not HOU_AVAILABLE:
        return None
    try:
        import hou

        desktop = hou.ui.curDesktop()
        errors = []

        # Collect every SceneViewer pane tab
        viewers = []

        try:
            import toolutils

            sv = toolutils.sceneViewer()
            if sv:
                viewers.append(sv)
        except Exception:
            pass

        try:
            for pane in desktop.paneTabs():
                try:
                    if pane.type() == hou.paneTabType.SceneViewer and pane not in viewers:
                        viewers.append(pane)
                except Exception:
                    pass
        except Exception:
            pass

        if not viewers and desktop:
            try:
                single = desktop.paneTabOfType(hou.paneTabType.SceneViewer)
                if single and single not in viewers:
                    viewers.append(single)
            except Exception:
                pass

        if not viewers:
            return None

        # Try each viewer in turn; prefer the one that is already current.
        def _viewer_priority(v):
            try:
                return 0 if v.isCurrentTab() else 1
            except Exception:
                return 1

        viewers.sort(key=_viewer_priority)

        for viewer in viewers:
            # Ensure this viewer is the active tab before framing or flipbooking.
            try:
                viewer.setIsCurrentTab()
                hou.ui.triggerUpdate()
                import time as _t

                _t.sleep(0.15)  # give Houdini time to switch and redraw
            except Exception:
                pass

            try:
                _frame_viewport(viewer)
                b64 = _flipbook_viewport(viewer, scale=scale)
                if b64:
                    return b64
            except Exception as e:
                errors.append(f"flipbook failed: {e!s}")

            # Fallback: grab an explicitly identifiable Scene Viewer widget.
            widget = _widget_for_pane(viewer)
            if widget:
                b64 = _grab_widget(widget, scale=scale)
                if b64:
                    return b64

            # Last fallback for this viewer: exact pane rectangle.
            bounds = _extract_screen_rect(viewer.screenBounds())
            if bounds:
                b64 = _grab_screen_rect(
                    bounds[0], bounds[1], bounds[2] - bounds[0], bounds[3] - bounds[1]
                )
                if b64:
                    return b64

        # Final non-invasive fallback: grab the visible Scene Viewer widget if
        # it exists but the pane lookup failed above.
        widget = _find_scene_viewer_widget()
        if widget is not None:
            b64 = _grab_widget(widget, scale=scale)
            if b64:
                return b64

        # ULTIMATE FALLBACK: If the layout is completely broken, maximized, or obscured,
        # forcefully spawn a floating SceneViewer, capture it, and close the floating window.
        if desktop:
            try:
                floating_pane = desktop.createFloatingPaneTab(hou.paneTabType.SceneViewer)
                if floating_pane:
                    import time as _t

                    hou.ui.triggerUpdate()
                    _t.sleep(0.3)  # Give OS time to map the new floating window
                    _frame_viewport(floating_pane)
                    b64 = _flipbook_viewport(floating_pane, scale=scale)
                    try:
                        floating_pane.pane().close()
                    except Exception:
                        floating_pane.close()
                    if b64:
                        return b64
            except Exception as e:
                errors.append(f"floating pane fallback failed: {e}")

        # If we reach here, absolutely everything failed. Raise so the agent can debug it.
        raise RuntimeError(f"All viewport capture methods failed. Debug info: {' | '.join(errors)}")
    except Exception as e:
        raise RuntimeError(f"capture_viewport fatal error: {e}")


def capture_main_window(scale: float = 0.5) -> str | None:
    """
    Capture the full Houdini main window as a fallback.
    Useful when pane-specific capture fails.
    """
    if not HOU_AVAILABLE:
        return None
    try:
        win = _find_houdini_main_window()
        if win is None:
            return None
        return _grab_widget(win, scale=scale)
    except Exception as e:
        print(f"[HoudiniMind Vision] capture_main_window error: {e}")
        return None


def capture_both(scale: float = 0.75) -> dict:
    """
    Capture both panes.
    Returns dict: { "network_editor": b64|None, "viewport": b64|None }
    Falls back to main window if both specific captures fail.
    """
    ne = capture_network_editor(scale=scale)
    vp = capture_viewport(scale=scale)

    # If both pane-specific grabs failed, grab the whole window
    if ne is None and vp is None:
        fallback = capture_main_window(scale=0.5)
        return {"network_editor": None, "viewport": None, "main_window_fallback": fallback}

    return {"network_editor": ne, "viewport": vp}


def b64_to_data_url(b64: str) -> str:
    """Convert raw base64 PNG string to a data-URL (for Qt image display)."""
    return f"data:image/png;base64,{b64}"
