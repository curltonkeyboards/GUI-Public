from collections import defaultdict

from PyQt5.QtGui import QPainter, QColor, QPainterPath, QTransform, QBrush, QPolygonF, QPalette, QPen, QPixmap, QFont
from PyQt5.QtWidgets import QWidget, QToolTip, QApplication
from PyQt5.QtCore import Qt, QSize, QRect, QPointF, pyqtSignal, QEvent, QRectF

from constants import KEY_SIZE_RATIO, KEY_SPACING_RATIO, KEYBOARD_WIDGET_PADDING, \
    KEYBOARD_WIDGET_MASK_HEIGHT, KEY_ROUNDNESS, SHADOW_SIDE_PADDING, SHADOW_TOP_PADDING, SHADOW_BOTTOM_PADDING, \
    KEYBOARD_WIDGET_NONMASK_PADDING
from themes import Theme
import themes2


class KeyWidget:

    def __init__(self, desc, scale, shift_x=0, shift_y=0):
        self.active = False
        self.on = False
        self.masked = False
        self.pressed = False
        self.desc = desc
        self.text = ""
        self.mask_text = ""
        self.tooltip = ""
        self.color = None
        self.mask_color = None
        self.scale = 0

        self.rotation_angle = desc.rotation_angle

        self.has2 = desc.width2 != desc.width or desc.height2 != desc.height or desc.x2 != 0 or desc.y2 != 0

        self.update_position(scale, shift_x, shift_y)

    def update_position(self, scale, shift_x=0, shift_y=0):
        if self.scale != scale or self.shift_x != shift_x or self.shift_y != shift_y:
            self.scale = scale
            self.size = self.scale * (KEY_SIZE_RATIO + KEY_SPACING_RATIO)
            spacing = self.scale * KEY_SPACING_RATIO

            self.rotation_x = self.size * self.desc.rotation_x
            self.rotation_y = self.size * self.desc.rotation_y

            self.shift_x = shift_x
            self.shift_y = shift_y
            self.x = self.size * self.desc.x
            self.y = self.size * self.desc.y
            self.w = self.size * self.desc.width - spacing
            self.h = self.size * self.desc.height - spacing

            self.rect = QRect(
                round(self.x),
                round(self.y),
                round(self.w),
                round(self.h)
            )
            self.text_rect = QRect(
                round(self.x),
                round(self.y + self.size * SHADOW_TOP_PADDING),
                round(self.w),
                round(self.h - self.size * (SHADOW_BOTTOM_PADDING + SHADOW_TOP_PADDING))
            )

            self.x2 = self.x + self.size * self.desc.x2
            self.y2 = self.y + self.size * self.desc.y2
            self.w2 = self.size * self.desc.width2 - spacing
            self.h2 = self.size * self.desc.height2 - spacing

            self.rect2 = QRect(
                round(self.x2),
                round(self.y2),
                round(self.w2),
                round(self.h2)
            )

            self.bbox = self.calculate_bbox(self.rect)
            self.bbox2 = self.calculate_bbox(self.rect2)
            self.polygon = QPolygonF(self.bbox + [self.bbox[0]])
            self.polygon2 = QPolygonF(self.bbox2 + [self.bbox2[0]])
            self.polygon = self.polygon.united(self.polygon2)
            self.corner = self.size * KEY_ROUNDNESS
            self.background_draw_path = self.calculate_background_draw_path()
            self.foreground_draw_path = self.calculate_foreground_draw_path()
            self.extra_draw_path = self.calculate_extra_draw_path()

            # calculate areas where the inner keycode will be located
            # nonmask = outer (e.g. Rsft_T)
            # mask = inner (e.g. KC_A)
            self.nonmask_rect = QRect(
                round(self.x),
                round(self.y + self.size * KEYBOARD_WIDGET_NONMASK_PADDING),
                round(self.w),
                round(self.h * (1 - KEYBOARD_WIDGET_MASK_HEIGHT))
            )
            self.mask_rect = QRect(
                round(self.x + self.size * SHADOW_SIDE_PADDING),
                round(self.y + self.h * (1 - KEYBOARD_WIDGET_MASK_HEIGHT)),
                round(self.w - 2 * self.size * SHADOW_SIDE_PADDING),
                round(self.h * KEYBOARD_WIDGET_MASK_HEIGHT - self.size * SHADOW_BOTTOM_PADDING)
            )
            self.mask_bbox = self.calculate_bbox(self.mask_rect)
            self.mask_polygon = QPolygonF(self.mask_bbox + [self.mask_bbox[0]])

    def calculate_bbox(self, rect):
        x1 = rect.topLeft().x()
        y1 = rect.topLeft().y()
        x2 = rect.bottomRight().x()
        y2 = rect.bottomRight().y()
        points = [(x1, y1), (x1, y2), (x2, y2), (x2, y1)]
        bbox = []
        for p in points:
            t = QTransform()
            t.translate(self.shift_x, self.shift_y)
            t.translate(self.rotation_x, self.rotation_y)
            t.rotate(self.rotation_angle)
            t.translate(-self.rotation_x, -self.rotation_y)
            p = t.map(QPointF(p[0], p[1]))
            bbox.append(p)
        return bbox

    def calculate_background_draw_path(self):
        path = QPainterPath()
        path.addRoundedRect(
            round(self.x),
            round(self.y),
            round(self.w),
            round(self.h),
            self.corner,
            self.corner
        )

        # second part only considered if different from first
        if self.has2:
            path2 = QPainterPath()
            path2.addRoundedRect(
                round(self.x2),
                round(self.y2),
                round(self.w2),
                round(self.h2),
                self.corner,
                self.corner
            )
            path = path.united(path2)

        return path

    def calculate_foreground_draw_path(self):
        path = QPainterPath()
        path.addRoundedRect(
            round(self.x + self.size * SHADOW_SIDE_PADDING),
            round(self.y + self.size * SHADOW_TOP_PADDING),
            round(self.w - 2 * self.size * SHADOW_SIDE_PADDING),
            round(self.h - self.size * (SHADOW_BOTTOM_PADDING + SHADOW_TOP_PADDING)),
            self.corner,
            self.corner
        )

        # second part only considered if different from first
        if self.has2:
            path2 = QPainterPath()
            path2.addRoundedRect(
                round(self.x2 + self.size * SHADOW_SIDE_PADDING),
                round(self.y2 + self.size * SHADOW_TOP_PADDING),
                round(self.w2 - 2 * self.size * SHADOW_SIDE_PADDING),
                round(self.h2 - self.size * (SHADOW_BOTTOM_PADDING + SHADOW_TOP_PADDING)),
                self.corner,
                self.corner
            )
            path = path.united(path2)

        return path

    def calculate_extra_draw_path(self):
        return QPainterPath()

    def setText(self, text):
        self.text = text

    def setMaskText(self, text):
        self.mask_text = text

    def setToolTip(self, tooltip):
        self.tooltip = tooltip

    def setActive(self, active):
        self.active = active

    def setOn(self, on):
        self.on = on

    def setPressed(self, pressed):
        self.pressed = pressed

    def setColor(self, color):
        self.color = color

    def setMaskColor(self, color):
        self.mask_color = color

    def __repr__(self):
        qualifiers = ["KeyboardWidget"]
        if self.desc.row is not None:
            qualifiers.append("matrix:{},{}".format(self.desc.row, self.desc.col))
        if self.desc.layout_index != -1:
            qualifiers.append("layout:{},{}".format(self.desc.layout_index, self.desc.layout_option))
        return " ".join(qualifiers)


class EncoderWidget(KeyWidget):

    def calculate_background_draw_path(self):
        path = QPainterPath()
        # Make encoder buttons circular
        path.addEllipse(round(self.x), round(self.y), round(self.w), round(self.h))
        return path

    def calculate_foreground_draw_path(self):
        path = QPainterPath()
        # Make encoder buttons circular
        path.addEllipse(
            round(self.x + self.size * SHADOW_SIDE_PADDING),
            round(self.y + self.size * SHADOW_TOP_PADDING),
            round(self.w - 2 * self.size * SHADOW_SIDE_PADDING),
            round(self.h - self.size * (SHADOW_BOTTOM_PADDING + SHADOW_TOP_PADDING))
        )
        return path

    def calculate_extra_draw_path(self):
        path = QPainterPath()
        # midpoint of arrow triangle
        p = self.h
        x = self.x
        y = self.y + p / 2
        if self.desc.encoder_dir == 0:
            # counterclockwise - pointing down
            path.moveTo(round(x), round(y))
            path.lineTo(round(x + p / 10), round(y - p / 10))
            path.lineTo(round(x), round(y + p / 10))
            path.lineTo(round(x - p / 10), round(y - p / 10))
            path.lineTo(round(x), round(y))
        else:
            # clockwise - pointing up
            path.moveTo(round(x), round(y))
            path.lineTo(round(x + p / 10), round(y + p / 10))
            path.lineTo(round(x), round(y - p / 10))
            path.lineTo(round(x - p / 10), round(y + p / 10))
            path.lineTo(round(x), round(y))
        return path

    def __repr__(self):
        return "EncoderWidget"


class KeyboardWidget(QWidget):

    clicked = pyqtSignal()
    deselected = pyqtSignal()
    anykey = pyqtSignal()

    def __init__(self, layout_editor):
        super().__init__()

        self.enabled = True
        self.scale = 1
        self.padding = KEYBOARD_WIDGET_PADDING

        # Set fixed font size for keyboard widget to maintain original key sizes
        fixed_font = QFont()
        fixed_font.setPointSize(8)
        self.setFont(fixed_font)

        self.setMouseTracking(True)

        self.layout_editor = layout_editor

        # widgets common for all layouts
        self.common_widgets = []

        # layout-specific widgets
        self.widgets_for_layout = []

        # widgets in current layout
        self.widgets = []

        self.width = self.height = 0
        self.active_key = None
        self.active_mask = False

    def set_keys(self, keys, encoders):
        self.common_widgets = []
        self.widgets_for_layout = []

        self.add_keys([(x, KeyWidget) for x in keys] + [(x, EncoderWidget) for x in encoders])
        self.update_layout()

    def add_keys(self, keys):
        scale_factor = self.fontMetrics().height()

        for key, cls in keys:
            if key.layout_index == -1:
                self.common_widgets.append(cls(key, scale_factor))
            else:
                self.widgets_for_layout.append(cls(key, scale_factor))

    def place_widgets(self):
        scale_factor = self.fontMetrics().height()

        self.widgets = []

        # place common widgets, that is, ones which are always displayed and require no extra transforms
        for widget in self.common_widgets:
            widget.update_position(scale_factor)
            self.widgets.append(widget)

        # top-left position for specific layout
        layout_x = defaultdict(lambda: defaultdict(lambda: 1e6))
        layout_y = defaultdict(lambda: defaultdict(lambda: 1e6))

        # determine top-left position for every layout option
        for widget in self.widgets_for_layout:
            widget.update_position(scale_factor)
            idx, opt = widget.desc.layout_index, widget.desc.layout_option
            p = widget.polygon.boundingRect().topLeft()
            layout_x[idx][opt] = min(layout_x[idx][opt], p.x())
            layout_y[idx][opt] = min(layout_y[idx][opt], p.y())

        # obtain widgets for all layout options now that we know how to shift them
        for widget in self.widgets_for_layout:
            idx, opt = widget.desc.layout_index, widget.desc.layout_option
            if opt == self.layout_editor.get_choice(idx):
                shift_x = layout_x[idx][opt] - layout_x[idx][0]
                shift_y = layout_y[idx][opt] - layout_y[idx][0]
                widget.update_position(scale_factor, -shift_x, -shift_y)
                self.widgets.append(widget)

        # at this point some widgets on left side might be cutoff, or there may be too much empty space
        # calculate top left position of visible widgets and shift everything around
        top_x = top_y = 1e6
        for widget in self.widgets:
            if not widget.desc.decal:
                p = widget.polygon.boundingRect().topLeft()
                top_x = min(top_x, p.x())
                top_y = min(top_y, p.y())
        for widget in self.widgets:
            widget.update_position(widget.scale, widget.shift_x - top_x + self.padding,
                                   widget.shift_y - top_y + self.padding)

    def update_layout(self):
        """ Updates self.widgets for the currently active layout """

        # determine widgets for current layout
        self.place_widgets()
        self.widgets = list(filter(lambda w: not w.desc.decal, self.widgets))

        self.widgets.sort(key=lambda w: (w.y, w.x))

        # determine maximum width and height of container
        max_w = max_h = 0
        for key in self.widgets:
            p = key.polygon.boundingRect().bottomRight()
            max_w = max(max_w, p.x() * self.scale)
            max_h = max(max_h, p.y() * self.scale)

        self.width = round(max_w + 2 * self.padding)
        self.height = round(max_h + 2 * self.padding)

        self.update()
        self.updateGeometry()

    def paintEvent(self, event):
        qp = QPainter()
        qp.begin(self)
        qp.setRenderHint(QPainter.Antialiasing)

        # for regular keycaps
        regular_pen = qp.pen()
        regular_pen.setColor(QApplication.palette().color(QPalette.ButtonText))
        qp.setPen(regular_pen)

        background_brush = QBrush()
        background_brush.setColor(QApplication.palette().color(QPalette.Button))
        background_brush.setStyle(Qt.SolidPattern)

        foreground_brush = QBrush()
        foreground_brush.setColor(QApplication.palette().color(QPalette.Button).lighter(120))
        foreground_brush.setStyle(Qt.SolidPattern)

        mask_brush = QBrush()
        mask_brush.setColor(QApplication.palette().color(QPalette.Button).lighter(Theme.mask_light_factor()))
        mask_brush.setStyle(Qt.SolidPattern)

        # for currently selected keycap
        active_pen = qp.pen()
        active_pen.setColor(QApplication.palette().color(QPalette.Highlight))
        active_pen.setWidthF(1.5)

        # for the encoder arrow
        extra_pen = regular_pen
        extra_brush = QBrush()
        extra_brush.setColor(QApplication.palette().color(QPalette.ButtonText))
        extra_brush.setStyle(Qt.SolidPattern)

        # for pressed keycaps
        background_pressed_brush = QBrush()
        background_pressed_brush.setColor(QApplication.palette().color(QPalette.Highlight))
        background_pressed_brush.setStyle(Qt.SolidPattern)

        foreground_pressed_brush = QBrush()
        foreground_pressed_brush.setColor(QApplication.palette().color(QPalette.Highlight).lighter(120))
        foreground_pressed_brush.setStyle(Qt.SolidPattern)

        background_on_brush = QBrush()
        background_on_brush.setColor(QApplication.palette().color(QPalette.Highlight).darker(150))
        background_on_brush.setStyle(Qt.SolidPattern)

        foreground_on_brush = QBrush()
        foreground_on_brush.setColor(QApplication.palette().color(QPalette.Highlight).darker(120))
        foreground_on_brush.setStyle(Qt.SolidPattern)

        mask_font = qp.font()
        mask_font.setPointSize(round(mask_font.pointSize() * 0.8))

        for idx, key in enumerate(self.widgets):
            qp.save()

            qp.scale(self.scale, self.scale)
            qp.translate(key.shift_x, key.shift_y)
            qp.translate(key.rotation_x, key.rotation_y)
            qp.rotate(key.rotation_angle)
            qp.translate(-key.rotation_x, -key.rotation_y)

            active = key.active or (self.active_key == key and not self.active_mask)

            # If this key has a custom color set (from per-key RGB painting), use it for entire key
            if key.color:
                # No border - just paint the key with radial gradient at 40% opacity
                qp.setPen(Qt.NoPen)

                # Create radial gradient brush for modern look (brighter center, darker edges)
                # Apply 40% opacity to all colors
                color = key.color
                r, g, b = color.red(), color.green(), color.blue()
                opacity = int(255 * 0.4)  # 40% opacity

                # Stronger darkening for better visibility
                r_dark = max(0, r - 60)
                g_dark = max(0, g - 60)
                b_dark = max(0, b - 60)

                from PyQt5.QtGui import QRadialGradient
                # Center the gradient on the key
                center_x = key.x + key.w / 2
                center_y = key.y + key.h / 2
                radius = max(key.w, key.h) * 0.7

                gradient = QRadialGradient(center_x, center_y, radius, center_x, center_y)
                gradient.setColorAt(0, QColor(r, g, b, opacity))  # Bright center with opacity
                gradient.setColorAt(1, QColor(r_dark, g_dark, b_dark, opacity))  # Dark edges with opacity

                gradient_brush = QBrush(gradient)
                qp.setBrush(gradient_brush)
                qp.drawPath(key.background_draw_path)
                # Don't draw foreground path to avoid overlap - single uniform 40% opacity layer
            else:
                # Default theme-based rendering for unpainted keys
                # draw keycap background/drop-shadow
                # For encoder widgets and push buttons, draw 2px border with QPalette.Window color when not active
                if (isinstance(key, EncoderWidget2) or isinstance(key, EncoderWidget) or
                    (hasattr(key.desc, 'row') and key.desc.row == 5 and key.desc.col in [0, 1, 2])):
                    if active:
                        qp.setPen(active_pen)
                    else:
                        border_pen = QPen(QApplication.palette().color(QPalette.Window))
                        border_pen.setWidth(2)
                        qp.setPen(border_pen)
                else:
                    qp.setPen(active_pen if active else Qt.NoPen)

                brush = background_brush
                if key.pressed:
                    brush = background_pressed_brush
                elif key.on:
                    brush = background_on_brush
                qp.setBrush(brush)
                qp.drawPath(key.background_draw_path)

                # draw keycap foreground
                qp.setPen(Qt.NoPen)
                brush = foreground_brush
                if key.pressed:
                    brush = foreground_pressed_brush
                elif key.on:
                    brush = foreground_on_brush

                qp.setBrush(brush)
                qp.drawPath(key.foreground_draw_path)

            # draw key text
            if key.masked:
                # draw the outer legend
                qp.setFont(mask_font)
                qp.setPen(key.color if key.color else regular_pen)
                qp.drawText(key.nonmask_rect, Qt.AlignCenter, key.text)

                # draw the inner highlight rect
                qp.setPen(active_pen if self.active_key == key and self.active_mask else Qt.NoPen)
                qp.setBrush(mask_brush)
                qp.drawRoundedRect(key.mask_rect, key.corner, key.corner)

                # draw the inner legend
                qp.setPen(key.mask_color if key.mask_color else regular_pen)
                qp.drawText(key.mask_rect, Qt.AlignCenter, key.mask_text)
            else:
                # draw the legend
                qp.setPen(key.color if key.color else regular_pen)
                qp.drawText(key.text_rect, Qt.AlignCenter, key.text)

            # draw the extra shape (encoder arrow)
            qp.setPen(extra_pen)
            qp.setBrush(extra_brush)
            qp.drawPath(key.extra_draw_path)

            qp.restore()

        qp.end()

    def minimumSizeHint(self):
        return QSize(self.width, self.height)

    def hit_test(self, pos):
        """ Returns key, hit_masked_part """

        for key in self.widgets:
            if key.masked and key.mask_polygon.containsPoint(pos/self.scale, Qt.OddEvenFill):
                return key, True
            if key.polygon.containsPoint(pos/self.scale, Qt.OddEvenFill):
                return key, False

        return None, False

    def mousePressEvent(self, ev):
        if not self.enabled:
            return

        self.active_key, self.active_mask = self.hit_test(ev.pos())
        if self.active_key is not None:
            self.clicked.emit()
        else:
            self.deselected.emit()
        self.update()

    def resizeEvent(self, ev):
        if self.isEnabled():
            self.update_layout()

    def select_next(self):
        """ Selects next key based on their order in the keymap """

        keys_looped = self.widgets + [self.widgets[0]]
        for x, key in enumerate(keys_looped):
            if key == self.active_key:
                self.active_key = keys_looped[x + 1]
                self.active_mask = False
                self.clicked.emit()
                return

    def deselect(self):
        if self.active_key is not None:
            self.active_key = None
            self.deselected.emit()
            self.update()

    def event(self, ev):
        if not self.enabled:
            super().event(ev)

        if ev.type() == QEvent.ToolTip:
            key = self.hit_test(ev.pos())[0]
            if key is not None:
                QToolTip.showText(ev.globalPos(), key.tooltip)
            else:
                QToolTip.hideText()
        elif ev.type() == QEvent.LayoutRequest:
            self.update_layout()
        elif ev.type() == QEvent.MouseButtonDblClick and self.active_key:
            self.anykey.emit()
        return super().event(ev)

    def set_enabled(self, val):
        self.enabled = val

    def set_scale(self, scale):
        self.scale = scale

    def get_scale(self):
        return self.scale


class KeyWidget2:

    def __init__(self, desc, scale, shift_x=0, shift_y=0):
        self.active = False
        self.on = False
        self.masked = False
        self.pressed = False
        self.desc = desc
        self.text = ""
        self.mask_text = ""
        self.tooltip = ""
        self.color = None
        self.mask_color = None
        self.scale = 0
        self.adc_value = None  # ADC value for matrix tester (None = not shown, 0-4095 = value)

        self.rotation_angle = desc.rotation_angle

        self.has2 = desc.width2 != desc.width or desc.height2 != desc.height or desc.x2 != 0 or desc.y2 != 0

        self.update_position(scale, shift_x, shift_y)

    def update_position(self, scale, shift_x=0, shift_y=0):
        if self.scale != scale or self.shift_x != shift_x or self.shift_y != shift_y:
            self.scale = scale
            self.size = self.scale * (KEY_SIZE_RATIO + KEY_SPACING_RATIO)
            spacing = self.scale * KEY_SPACING_RATIO

            self.rotation_x = self.size * self.desc.rotation_x
            self.rotation_y = self.size * self.desc.rotation_y

            self.shift_x = shift_x
            self.shift_y = shift_y
            self.x = self.size * self.desc.x
            self.y = self.size * self.desc.y
            self.w = self.size * self.desc.width - spacing
            self.h = self.size * self.desc.height - spacing

            self.rect = QRect(
                round(self.x),
                round(self.y),
                round(self.w),
                round(self.h)
            )
            self.text_rect = QRect(
                round(self.x),
                round(self.y + self.size * SHADOW_TOP_PADDING),
                round(self.w),
                round(self.h - self.size * (SHADOW_BOTTOM_PADDING + SHADOW_TOP_PADDING))
            )

            self.x2 = self.x + self.size * self.desc.x2
            self.y2 = self.y + self.size * self.desc.y2
            self.w2 = self.size * self.desc.width2 - spacing
            self.h2 = self.size * self.desc.height2 - spacing

            self.rect2 = QRect(
                round(self.x2),
                round(self.y2),
                round(self.w2),
                round(self.h2)
            )

            self.bbox = self.calculate_bbox(self.rect)
            self.bbox2 = self.calculate_bbox(self.rect2)
            self.polygon = QPolygonF(self.bbox + [self.bbox[0]])
            self.polygon2 = QPolygonF(self.bbox2 + [self.bbox2[0]])
            self.polygon = self.polygon.united(self.polygon2)
            self.corner = self.size * KEY_ROUNDNESS
            self.background_draw_path = self.calculate_background_draw_path()
            self.foreground_draw_path = self.calculate_foreground_draw_path()
            self.extra_draw_path = self.calculate_extra_draw_path()

            # calculate areas where the inner keycode will be located
            # nonmask = outer (e.g. Rsft_T)
            # mask = inner (e.g. KC_A)
            self.nonmask_rect = QRect(
                round(self.x),
                round(self.y + self.size * KEYBOARD_WIDGET_NONMASK_PADDING),
                round(self.w),
                round(self.h * (1 - KEYBOARD_WIDGET_MASK_HEIGHT))
            )
            self.mask_rect = QRect(
                round(self.x + self.size * SHADOW_SIDE_PADDING),
                round(self.y + self.h * (1 - KEYBOARD_WIDGET_MASK_HEIGHT)),
                round(self.w - 2 * self.size * SHADOW_SIDE_PADDING),
                round(self.h * KEYBOARD_WIDGET_MASK_HEIGHT - self.size * SHADOW_BOTTOM_PADDING)
            )
            self.mask_bbox = self.calculate_bbox(self.mask_rect)
            self.mask_polygon = QPolygonF(self.mask_bbox + [self.mask_bbox[0]])

    def calculate_bbox(self, rect):
        x1 = rect.topLeft().x()
        y1 = rect.topLeft().y()
        x2 = rect.bottomRight().x()
        y2 = rect.bottomRight().y()
        points = [(x1, y1), (x1, y2), (x2, y2), (x2, y1)]
        bbox = []
        for p in points:
            t = QTransform()
            t.translate(self.shift_x, self.shift_y)
            t.translate(self.rotation_x, self.rotation_y)
            t.rotate(self.rotation_angle)
            t.translate(-self.rotation_x, -self.rotation_y)
            p = t.map(QPointF(p[0], p[1]))
            bbox.append(p)
        return bbox

    def calculate_background_draw_path(self):
        path = QPainterPath()
        path.addRoundedRect(
            round(self.x),
            round(self.y),
            round(self.w),
            round(self.h),
            self.corner,
            self.corner
        )

        # second part only considered if different from first
        if self.has2:
            path2 = QPainterPath()
            path2.addRoundedRect(
                round(self.x2),
                round(self.y2),
                round(self.w2),
                round(self.h2),
                self.corner,
                self.corner
            )
            path = path.united(path2)

        return path

    def calculate_foreground_draw_path(self):
        path = QPainterPath()
        path.addRoundedRect(
            round(self.x + self.size * SHADOW_SIDE_PADDING),
            round(self.y + self.size * SHADOW_TOP_PADDING),
            round(self.w - 2 * self.size * SHADOW_SIDE_PADDING),
            round(self.h - self.size * (SHADOW_BOTTOM_PADDING + SHADOW_TOP_PADDING)),
            self.corner,
            self.corner
        )

        # second part only considered if different from first
        if self.has2:
            path2 = QPainterPath()
            path2.addRoundedRect(
                round(self.x2 + self.size * SHADOW_SIDE_PADDING),
                round(self.y2 + self.size * SHADOW_TOP_PADDING),
                round(self.w2 - 2 * self.size * SHADOW_SIDE_PADDING),
                round(self.h2 - self.size * (SHADOW_BOTTOM_PADDING + SHADOW_TOP_PADDING)),
                self.corner,
                self.corner
            )
            path = path.united(path2)

        return path

    def calculate_extra_draw_path(self):
        return QPainterPath()

    def setText(self, text):
        self.text = text

    def setMaskText(self, text):
        self.mask_text = text

    def setToolTip(self, tooltip):
        self.tooltip = tooltip

    def setActive(self, active):
        self.active = active

    def setOn(self, on):
        self.on = on

    def setPressed(self, pressed):
        self.pressed = pressed

    def setColor(self, color):
        self.color = color

    def setMaskColor(self, color):
        self.mask_color = color

    def setAdcValue(self, value):
        """Set ADC value for matrix tester display (None to hide, 0-4095 for value)"""
        self.adc_value = value

    def __repr__(self):
        qualifiers = ["KeyboardWidget2"]
        if self.desc.row is not None:
            qualifiers.append("matrix:{},{}".format(self.desc.row, self.desc.col))
        if self.desc.layout_index != -1:
            qualifiers.append("layout:{},{}".format(self.desc.layout_index, self.desc.layout_option))
        return " ".join(qualifiers)


class EncoderWidget2(KeyWidget2):

    def calculate_background_draw_path(self):
        path = QPainterPath()
        # Make encoder buttons circular
        path.addEllipse(round(self.x), round(self.y), round(self.w), round(self.h))
        return path

    def calculate_foreground_draw_path(self):
        path = QPainterPath()
        # Make encoder buttons circular
        path.addEllipse(
            round(self.x + self.size * SHADOW_SIDE_PADDING),
            round(self.y + self.size * SHADOW_TOP_PADDING),
            round(self.w - 2 * self.size * SHADOW_SIDE_PADDING),
            round(self.h - self.size * (SHADOW_BOTTOM_PADDING + SHADOW_TOP_PADDING))
        )
        return path

    def calculate_extra_draw_path(self):
        path = QPainterPath()
        # midpoint of arrow triangle
        p = self.h
        x = self.x + self.w / 2  # Centered on the widget width
        y = self.y  # Align with the top of the widget

        if self.desc.encoder_dir == 0:
            # counterclockwise - pointing up (flipped)
            path.moveTo(round(x), round(y))
            path.lineTo(round(x + p / 10), round(y - p / 10))  # Flipped
            path.lineTo(round(x), round(y + p / 10))           # Flipped
            path.lineTo(round(x - p / 10), round(y - p / 10))  # Flipped
            path.lineTo(round(x), round(y))
        else:
            # clockwise - pointing down (flipped)
            path.moveTo(round(x), round(y))
            path.lineTo(round(x + p / 10), round(y + p / 10))  # Flipped
            path.lineTo(round(x), round(y - p / 10))           # Flipped
            path.lineTo(round(x - p / 10), round(y + p / 10))  # Flipped
            path.lineTo(round(x), round(y))
        return path

    def __repr__(self):
        return "EncoderWidget2"




class KeyboardWidget2(QWidget):

    clicked = pyqtSignal()
    deselected = pyqtSignal()
    anykey = pyqtSignal()

    def __init__(self, layout_editor):
        super().__init__()

        self.enabled = True
        self.scale = 1
        self.padding = KEYBOARD_WIDGET_PADDING

        # Set fixed font size for keyboard widget to maintain original key sizes
        fixed_font = QFont()
        fixed_font.setPointSize(8)
        self.setFont(fixed_font)

        themes2.qInitResources()
        self.setMouseTracking(True)

        self.layout_editor = layout_editor

        # widgets common for all layouts
        self.common_widgets = []

        # layout-specific widgets
        self.widgets_for_layout = []

        # widgets in current layout
        self.widgets = []

        self.width = self.height = 0
        self.active_key = None
        self.active_mask = False
        self.is_dragging = False  # Track if we're drag-selecting
        self.drag_mode = None  # 'select' or 'deselect'

        # Multi-selection support
        self.selected_keys = set()  # Set of selected key widgets

    def set_keys(self, keys, encoders):
        self.common_widgets = []
        self.widgets_for_layout = []

        self.add_keys([(x, KeyWidget2) for x in keys] + [(x, EncoderWidget2) for x in encoders])
        self.update_layout()

    def add_keys(self, keys):
        scale_factor = self.fontMetrics().height()

        for key, cls in keys:
            if key.layout_index == -1:
                self.common_widgets.append(cls(key, scale_factor))
            else:
                self.widgets_for_layout.append(cls(key, scale_factor))

    def place_widgets(self):
        scale_factor = self.fontMetrics().height()

        self.widgets = []

        # place common widgets, that is, ones which are always displayed and require no extra transforms
        for widget in self.common_widgets:
            widget.update_position(scale_factor)
            self.widgets.append(widget)

        # top-left position for specific layout
        layout_x = defaultdict(lambda: defaultdict(lambda: 1e6))
        layout_y = defaultdict(lambda: defaultdict(lambda: 1e6))

        # determine top-left position for every layout option
        for widget in self.widgets_for_layout:
            widget.update_position(scale_factor)
            idx, opt = widget.desc.layout_index, widget.desc.layout_option
            p = widget.polygon.boundingRect().topLeft()
            layout_x[idx][opt] = min(layout_x[idx][opt], p.x())
            layout_y[idx][opt] = min(layout_y[idx][opt], p.y())

        # obtain widgets for all layout options now that we know how to shift them
        for widget in self.widgets_for_layout:
            idx, opt = widget.desc.layout_index, widget.desc.layout_option
            if opt == self.layout_editor.get_choice(idx):
                shift_x = layout_x[idx][opt] - layout_x[idx][0]
                shift_y = layout_y[idx][opt] - layout_y[idx][0]
                widget.update_position(scale_factor, -shift_x, -shift_y)
                self.widgets.append(widget)

        # at this point some widgets on left side might be cutoff, or there may be too much empty space
        # calculate top left position of visible widgets and shift everything around
        top_x = top_y = 1e6
        for widget in self.widgets:
            if not widget.desc.decal:
                p = widget.polygon.boundingRect().topLeft()
                top_x = min(top_x, p.x())
                top_y = min(top_y, p.y())
        for widget in self.widgets:
            widget.update_position(widget.scale, widget.shift_x - top_x + self.padding,
                                   widget.shift_y - top_y + self.padding)

    def update_layout(self):
        """ Updates self.widgets for the currently active layout """

        # Determine widgets for the current layout
        self.place_widgets()
        self.widgets = list(filter(lambda w: not w.desc.decal, self.widgets))

        # Filter out encoder widgets and row 5 widgets (encoder click buttons and sustain pedal)
        # These will be shown in the EncoderAssignWidget instead
        self.widgets = [w for w in self.widgets if not isinstance(w, EncoderWidget2) and
                        not (hasattr(w.desc, 'row') and w.desc.row == 5)]

        # Sort widgets by position for proper layout (if needed)
        self.widgets.sort(key=lambda w: (w.y, w.x))

        # Determine maximum width and height of the container
        max_w = max_h = 0
        for key in self.widgets:
            p = key.polygon.boundingRect().bottomRight()
            max_w = max(max_w, p.x() * (self.scale * 1.4))
            max_h = max(max_h, p.y() * (self.scale * 1.5))

        # Move all widgets right and down to create proper padding
        for widget in self.widgets:
            widget.shift_x += 30  # Move right 30 pixels
            widget.shift_y += 20  # Move down 20 pixels

        self.width = round(max_w + 2 * self.padding)
        self.height = round(max_h + 2 * self.padding)

        self.update()
        self.updateGeometry()

    def paintEvent(self, event):
        qp = QPainter()
        qp.begin(self)
        qp.setRenderHint(QPainter.Antialiasing)
        
        # Set up the color and pen for the keyboard border
        border_pen = QPen(QApplication.palette().color(QPalette.Highlight))
        border_pen.setWidth(3)  # Set width of the border
        qp.setPen(border_pen)
        qp.setBrush(Qt.NoBrush)
        
        def with_transparency(color, transparency_factor):
            alpha = int(255 * (1 - transparency_factor))
            return QColor(color.red(), color.green(), color.blue(), alpha)
    
        # Draw the rounded border around the keyboard
        border_radius = 15  # Radius for rounded corners
        rect = QRect(self.padding, self.padding, self.width - 2 * self.padding, self.height - 2 * self.padding)
        qp.drawRoundedRect(rect, border_radius, border_radius)

        # Get the Window color and calculate brightness to determine light or dark theme
        window_color = QApplication.palette().color(QPalette.Window)
        brightness = (window_color.red() * 0.299 + window_color.green() * 0.587 + window_color.blue() * 0.114)

        # Choose image based on brightness (light or dark theme)
        if brightness > 127:  # Threshold for light/dark theme
            pixmap = QPixmap(":/backgroundlight")  # Light theme alias
        else:
            pixmap = QPixmap(":/backgrounddark")  # Dark theme alias
        
        if not pixmap.isNull():
            # Define the area for the image with specific coordinates and dimensions
            image_x, image_y = 0, 0  # Adjust as needed for positioning
            image_width, image_height = 1035, 345  # Set the dimensions as desired
            image_rect = QRect(image_x, image_y, image_width, image_height)  # Use QRect instead of QRectF

            # Create a rounded path for clipping
            path = QPainterPath()
            path.addRoundedRect(QRectF(image_rect), 15.0, 15.0)  # Use QRectF here for rounded corners

            # Clip drawing to the rounded rectangle path and draw the image
            qp.setClipPath(path)
            qp.drawPixmap(image_rect, pixmap, pixmap.rect())

        # Reset clipping after drawing the image
        qp.setClipping(False)

        # for regular keycaps
        regular_pen = qp.pen()
        regular_pen.setColor(QApplication.palette().color(QPalette.ButtonText))
        qp.setPen(regular_pen)

        background_brush = QBrush()
        background_color = QApplication.palette().color(QPalette.Button)
        background_brush.setColor(with_transparency(background_color, 0.99))  # 70% transparent
        background_brush.setStyle(Qt.SolidPattern)

        # Foreground brush
        foreground_brush = QBrush()
        foreground_color = QApplication.palette().color(QPalette.Button)
        foreground_brush.setColor(with_transparency(foreground_color, 0.99))  # 70% transparent
        foreground_brush.setStyle(Qt.SolidPattern)

        # Mask brush
        mask_brush = QBrush()
        mask_color = QApplication.palette().color(QPalette.Button).lighter(Theme.mask_light_factor())
        mask_brush.setColor(with_transparency(mask_color, 0.01))  # 70% transparent
        mask_brush.setStyle(Qt.SolidPattern)

        # for currently selected keycap
        active_pen = qp.pen()
        active_pen.setColor(QColor("#fabcad"))  # Set color with a hex code
        active_pen.setWidthF(1.5)

        # for the encoder arrow
        extra_pen = regular_pen
        extra_brush = QBrush()
        extra_brush.setColor(QApplication.palette().color(QPalette.ButtonText))
        extra_brush.setStyle(Qt.SolidPattern)

        # for pressed keycaps
        background_pressed_brush = QBrush()
        background_pressed_brush.setColor(QApplication.palette().color(QPalette.Highlight))
        background_pressed_brush.setStyle(Qt.SolidPattern)

        foreground_pressed_brush = QBrush()
        foreground_pressed_brush.setColor(QApplication.palette().color(QPalette.Highlight).lighter(120))
        foreground_pressed_brush.setStyle(Qt.SolidPattern)

        background_on_brush = QBrush()
        background_on_brush.setColor(QApplication.palette().color(QPalette.Highlight).darker(150))
        background_on_brush.setStyle(Qt.SolidPattern)

        foreground_on_brush = QBrush()
        foreground_on_brush.setColor(QApplication.palette().color(QPalette.Highlight).darker(120))
        foreground_on_brush.setStyle(Qt.SolidPattern)

        mask_font = qp.font()
        #doesnt seem to change font size
        mask_font.setPointSize(round(mask_font.pointSize() * 1.8))

        for idx, key in enumerate(self.widgets):
            qp.save()

            qp.scale(self.scale * 1.3, self.scale * 1.3)
            qp.translate(key.shift_x, key.shift_y)
            qp.translate(key.rotation_x, key.rotation_y)
            qp.rotate(key.rotation_angle)
            qp.translate(-key.rotation_x, -key.rotation_y)

            # Check if key is active (selected or is the current active key)
            active = key.active or (self.active_key == key and not self.active_mask) or (key in self.selected_keys)

            # If this key has a custom color set (from per-key RGB painting), use it for entire key
            if key.color:
                # Show border when active/selected - enable highlighting for rapidfire keys
                qp.setPen(active_pen if active else Qt.NoPen)

                # Create radial gradient brush for modern look (brighter center, darker edges)
                # Apply 25% opacity for more transparency and better theme integration
                color = key.color
                r, g, b = color.red(), color.green(), color.blue()
                opacity = int(255 * 0.25)  # 25% opacity - more transparent and theme-related

                # Stronger darkening for better visibility
                r_dark = max(0, r - 60)
                g_dark = max(0, g - 60)
                b_dark = max(0, b - 60)

                from PyQt5.QtGui import QRadialGradient
                # Center the gradient on the key
                center_x = key.x + key.w / 2
                center_y = key.y + key.h / 2
                radius = max(key.w, key.h) * 0.7

                gradient = QRadialGradient(center_x, center_y, radius, center_x, center_y)
                gradient.setColorAt(0, QColor(r, g, b, opacity))  # Bright center with opacity
                gradient.setColorAt(1, QColor(r_dark, g_dark, b_dark, opacity))  # Dark edges with opacity

                gradient_brush = QBrush(gradient)
                qp.setBrush(gradient_brush)
                qp.drawPath(key.background_draw_path)
                # Don't draw foreground path to avoid overlap - single uniform opacity layer
            else:
                # Default theme-based rendering for unpainted keys
                # draw keycap background/drop-shadow
                qp.setPen(active_pen if active else Qt.NoPen)

                brush = background_brush
                if key.pressed:
                    brush = background_pressed_brush
                elif key.on:
                    brush = background_on_brush
                qp.setBrush(brush)
                qp.drawPath(key.background_draw_path)

                # draw keycap foreground
                qp.setPen(Qt.NoPen)
                brush = foreground_brush
                if key.pressed:
                    brush = foreground_pressed_brush
                elif key.on:
                    brush = foreground_on_brush

                qp.setBrush(brush)
                qp.drawPath(key.foreground_draw_path)

            # draw key text
            if key.masked:
                # draw the outer legend doesnt seem to change font size
                qp.setFont(mask_font)
                qp.setPen(regular_pen)  # Always use regular text color, even for colored keys
                qp.drawText(key.nonmask_rect, Qt.AlignCenter, key.text)

                # draw the inner highlight rect
                qp.setPen(active_pen if self.active_key == key and self.active_mask else Qt.NoPen)
                qp.setBrush(mask_brush)
                qp.drawRoundedRect(key.mask_rect, key.corner, key.corner)

                # draw the inner legend
                qp.setPen(key.mask_color if key.mask_color else regular_pen)
                smaller_font = qp.font()
                smaller_font.setPointSize(smaller_font.pointSize() - 1)
                qp.setFont(smaller_font)
                qp.drawText(key.mask_rect, Qt.AlignCenter, key.mask_text)
            else:
                # draw the legend - always use regular text color, even for colored keys
                qp.setPen(regular_pen)
                smaller_font = qp.font()
                smaller_font.setPointSize(smaller_font.pointSize() - 1)
                qp.setFont(smaller_font)
                qp.drawText(key.text_rect, Qt.AlignCenter, key.text)

            # draw ADC value if set (for matrix tester)
            if key.adc_value is not None:
                adc_font = qp.font()
                adc_font.setPointSize(max(6, adc_font.pointSize() - 2))
                adc_font.setBold(True)
                qp.setFont(adc_font)
                # Green when pressed (actuation met), otherwise white/black based on theme
                if key.pressed:
                    qp.setPen(QColor("#00FF00"))
                else:
                    # Check if light theme (white text needs dark bg, black text needs light bg)
                    light_themes = ["Light", "Lavender Dream", "Mint Fresh", "Peachy Keen", "Sky Serenity", "Rose Garden"]
                    is_light = Theme.get_theme() in light_themes
                    qp.setPen(QColor("#000000") if is_light else QColor("#FFFFFF"))
                # Create a rect at the bottom of the key for ADC value
                adc_rect = QRect(
                    round(key.x),
                    round(key.y + key.h * 0.65),
                    round(key.w),
                    round(key.h * 0.30)
                )
                qp.drawText(adc_rect, Qt.AlignCenter, str(key.adc_value))

            # draw the extra shape (encoder arrow)
            qp.setPen(extra_pen)
            qp.setBrush(extra_brush)
            qp.drawPath(key.extra_draw_path)

            qp.restore()

        qp.end()

    def minimumSizeHint(self):
        return QSize(self.width, self.height)

    def hit_test(self, pos):
        """ Returns key, hit_masked_part """

        # Adjust the position for hit testing based on shifts
        adjusted_pos = pos / (self.scale * 1.3)

        for key in self.widgets:
            # Check the masked hitbox first
            if key.masked and key.mask_polygon.containsPoint(adjusted_pos - QPointF(key.shift_x, key.shift_y), Qt.OddEvenFill):
                return key, True
            # Then check the regular hitbox
            if key.polygon.containsPoint(adjusted_pos - QPointF(key.shift_x, key.shift_y), Qt.OddEvenFill):
                return key, False

        return None, False


    def mousePressEvent(self, ev):
        if not self.enabled:
            return

        clicked_key, self.active_mask = self.hit_test(ev.pos())
        if clicked_key is not None:
            # Start drag mode
            self.is_dragging = True

            # Determine drag mode based on current selection state
            if clicked_key in self.selected_keys:
                # Clicking on already selected key - start deselect mode
                self.drag_mode = 'deselect'
                self.selected_keys.remove(clicked_key)
                # If this was the last selected key, deselect entirely
                if not self.selected_keys:
                    self.active_key = None
                    self.deselected.emit()
                else:
                    # Set active_key to one of the remaining selected keys
                    self.active_key = next(iter(self.selected_keys))
                    self.clicked.emit()
            else:
                # Clicking on unselected key - start select mode
                self.drag_mode = 'select'
                self.selected_keys.add(clicked_key)
                self.active_key = clicked_key
                self.clicked.emit()
        else:
            # Clicked empty space - clear selection
            self.selected_keys.clear()
            self.active_key = None
            self.is_dragging = False
            self.drag_mode = None
            self.deselected.emit()
        self.update()

    def mouseMoveEvent(self, ev):
        """Handle mouse move for drag selecting/deselecting"""
        if not self.enabled or not self.is_dragging or self.drag_mode is None:
            return

        # Check if we're over a key
        key, mask = self.hit_test(ev.pos())
        if key is not None and not isinstance(key, EncoderWidget2):
            if self.drag_mode == 'select':
                # Add key to selection if not already selected
                if key not in self.selected_keys:
                    self.selected_keys.add(key)
                    self.active_key = key
                    self.active_mask = mask
                    self.clicked.emit()
                    self.update()
            elif self.drag_mode == 'deselect':
                # Remove key from selection if currently selected
                if key in self.selected_keys:
                    self.selected_keys.remove(key)
                    if self.selected_keys:
                        self.active_key = next(iter(self.selected_keys))
                    else:
                        self.active_key = None
                    self.active_mask = mask
                    self.clicked.emit()
                    self.update()

    def mouseReleaseEvent(self, ev):
        """Handle mouse release to stop drag selecting/deselecting"""
        if not self.enabled:
            return

        self.is_dragging = False
        self.drag_mode = None

    def resizeEvent(self, ev):
        if self.isEnabled():
            self.update_layout()

    def select_next(self):
        """ Selects next key based on their order in the keymap, skipping EncoderWidget2s """
    
        # Loop through widgets, with wraparound to start
        keys_looped = self.widgets + [self.widgets[0]]
        for x, key in enumerate(keys_looped):
            if key == self.active_key:
                # Find the next widget that is not an EncoderWidget2
                for next_key in keys_looped[x + 1:]:
                    if not isinstance(next_key, EncoderWidget2):
                        self.active_key = next_key
                        self.active_mask = False
                        self.clicked.emit()
                        return


    def deselect(self):
        if self.active_key is not None:
            self.active_key = None
            self.deselected.emit()
            self.update()

    def event(self, ev):
        if not self.enabled:
            super().event(ev)

        if ev.type() == QEvent.ToolTip:
            key = self.hit_test(ev.pos())[0]
            if key is not None:
                QToolTip.showText(ev.globalPos(), key.tooltip)
            else:
                QToolTip.hideText()
        elif ev.type() == QEvent.LayoutRequest:
            self.update_layout()
        elif ev.type() == QEvent.MouseButtonDblClick and self.active_key:
            self.anykey.emit()
        return super().event(ev)

    def set_enabled(self, val):
        self.enabled = val

    def set_scale(self, scale):
        self.scale = scale

    def get_scale(self):
        return self.scale

    def select_all(self):
        """Select all keys (excluding encoders)"""
        self.selected_keys.clear()
        for widget in self.widgets:
            if not isinstance(widget, EncoderWidget2):
                self.selected_keys.add(widget)
        if self.selected_keys:
            self.active_key = next(iter(self.selected_keys))
            self.clicked.emit()
        self.update()

    def unselect_all(self):
        """Unselect all keys"""
        self.selected_keys.clear()
        self.active_key = None
        self.deselected.emit()
        self.update()

    def invert_selection(self):
        """Invert the current selection"""
        new_selection = set()
        for widget in self.widgets:
            if not isinstance(widget, EncoderWidget2):
                if widget not in self.selected_keys:
                    new_selection.add(widget)
        self.selected_keys = new_selection
        if self.selected_keys:
            self.active_key = next(iter(self.selected_keys))
            self.clicked.emit()
        else:
            self.active_key = None
            self.deselected.emit()
        self.update()

    def get_selected_keys(self):
        """Returns list of selected keys (or active key if no selection)"""
        if self.selected_keys:
            return list(self.selected_keys)
        elif self.active_key:
            return [self.active_key]
        return []


class KeyboardWidgetSimple(KeyboardWidget2):
    """
    Simplified version of KeyboardWidget2 with original selection behavior.
    Used by keymap, lighting, and layout editors that don't need multi-selection.

    This restores the pre-trigger-settings behavior where:
    - Click selects a single key
    - Drag paints over multiple keys sequentially
    - No multi-selection or drag-to-deselect modes
    """

    def __init__(self, layout_editor):
        # Call parent init which sets up all the widgets
        super().__init__(layout_editor)

        # Remove multi-selection features not needed for simple mode
        self.drag_mode = None
        self.selected_keys = set()

    def mousePressEvent(self, ev):
        """Original simple mouse press behavior: click to select, drag to paint"""
        if not self.enabled:
            return

        self.active_key, self.active_mask = self.hit_test(ev.pos())
        if self.active_key is not None:
            self.is_dragging = True  # Start drag painting
            self.clicked.emit()
        else:
            self.deselected.emit()
        self.update()

    def mouseMoveEvent(self, ev):
        """Original drag painting: drag over keys to select them sequentially"""
        if not self.enabled or not self.is_dragging:
            return

        # Check if we're over a key
        key, mask = self.hit_test(ev.pos())
        if key is not None and key != self.active_key:
            # We've dragged onto a new key, paint it
            self.active_key = key
            self.active_mask = mask
            self.clicked.emit()
            self.update()

    def mouseReleaseEvent(self, ev):
        """Stop drag painting on mouse release"""
        if not self.enabled:
            return

        self.is_dragging = False


class KeyboardWidgetNoHighlight(KeyboardWidgetSimple):
    """
    Keyboard widget with no selection highlighting at all.
    Used by lighting/RGB configurator where color painting is done
    and selection highlighting would interfere with seeing the actual colors.

    Keys still emit clicked signals for interaction, but no visual highlighting.
    """

    def mousePressEvent(self, ev):
        """Click to interact with key, but don't highlight it"""
        if not self.enabled:
            return

        clicked_key, clicked_mask = self.hit_test(ev.pos())
        if clicked_key is not None:
            # Don't set active_key to avoid highlighting
            self.active_mask = clicked_mask
            self.is_dragging = True
            # Temporarily set active_key for the signal, then clear it
            self.active_key = clicked_key
            self.clicked.emit()
            self.active_key = None  # Clear immediately to prevent highlighting
        else:
            self.deselected.emit()
        self.update()

    def mouseMoveEvent(self, ev):
        """Drag over keys to interact, but don't highlight them"""
        if not self.enabled or not self.is_dragging:
            return

        key, mask = self.hit_test(ev.pos())
        if key is not None:
            # Allow dragging without highlighting
            self.active_mask = mask
            # Temporarily set for signal emission
            self.active_key = key
            self.clicked.emit()
            self.active_key = None  # Clear immediately
            self.update()

    def mouseReleaseEvent(self, ev):
        """Stop drag interaction on mouse release"""
        if not self.enabled:
            return

        self.is_dragging = False
        self.active_key = None  # Ensure no highlighting remains
