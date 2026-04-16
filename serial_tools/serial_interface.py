# coding:utf-8
import sys
import pyte
from datetime import datetime
import serial
import serial.tools.list_ports
from serial import Serial, SerialException
from PyQt6.QtGui import QFont, QKeyEvent, QTextCursor, QColor, QTextCharFormat, QAction
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QObject, QPropertyAnimation, QEasingCurve, QRect
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QStackedWidget,
    QLabel,
    QFileDialog,
    QFontDialog,
    QGraphicsOpacityEffect,
)

from qfluentwidgets import (
    FluentIcon as FIF,
    SegmentedWidget,
    InfoBar,
    InfoBarPosition,
    BodyLabel,
    ComboBox,
    PlainTextEdit,
    DropDownPushButton,
    RoundMenu,
    PushButton,
    ToggleButton,
    SpinBox,
    CheckBox,
    CompactSpinBox,
    RadioButton,
    setTheme,
    Theme,
    setThemeColor,
    TogglePushButton,
    StrongBodyLabel,
    ProgressRing,
)

import os
import sys
from settings.config import cfg

from ymodem.Socket import ModemSocket


class PyteTerminal:
    def __init__(self, columns=80, rows=24):
        self.columns = columns
        self.rows = rows
        self.screen = pyte.Screen(columns, rows)
        self.stream = pyte.Stream(self.screen)
        self._cursor_visible = True
        
    def feed(self, data):
        if isinstance(data, bytes):
            data = data.decode('utf-8', errors='replace')
        self.stream.feed(data)
        
    def get_display(self):
        lines = []
        for y in range(self.rows):
            line = ""
            for x in range(self.columns):
                char = self.screen.buffer[y][x]
                line += char.data if char.data else " "
            lines.append(line.rstrip())
        while lines and not lines[-1]:
            lines.pop()
        return "\n".join(lines)
    
    def get_formatted_lines(self):
        formatted_lines = []
        for y in range(self.rows):
            line_segments = []
            current_text = ""
            current_fg = None
            current_bg = None
            current_bold = False
            current_underline = False
            
            for x in range(self.columns):
                char = self.screen.buffer[y][x]
                fg = self._color_to_hex(char.fg) if char.fg != "default" else None
                bg = self._color_to_hex(char.bg) if char.bg != "default" else None
                bold = char.bold if hasattr(char, 'bold') else False
                underline = char.underline if hasattr(char, 'underline') else False
                
                if (fg != current_fg or bg != current_bg or 
                    bold != current_bold or underline != current_underline):
                    if current_text:
                        line_segments.append({
                            'text': current_text,
                            'fg': current_fg,
                            'bg': current_bg,
                            'bold': current_bold,
                            'underline': current_underline
                        })
                    current_text = char.data if char.data else " "
                    current_fg = fg
                    current_bg = bg
                    current_bold = bold
                    current_underline = underline
                else:
                    current_text += char.data if char.data else " "
            
            if current_text:
                line_segments.append({
                    'text': current_text.rstrip(),
                    'fg': current_fg,
                    'bg': current_bg,
                    'bold': current_bold,
                    'underline': current_underline
                })
            
            if line_segments:
                formatted_lines.append({'y': y, 'segments': line_segments})
        
        return formatted_lines
    
    def _color_to_hex(self, color):
        color_map = {
            'black': '#000000',
            'red': '#cd0000',
            'green': '#00cd00',
            'brown': '#cdcd00',
            'blue': '#0000ee',
            'magenta': '#cd00cd',
            'cyan': '#00cdcd',
            'white': '#e5e5e5',
            'brightblack': '#7f7f7f',
            'brightred': '#ff0000',
            'brightgreen': '#00ff00',
            'brightyellow': '#ffff00',
            'brightblue': '#5c5cff',
            'brightmagenta': '#ff00ff',
            'brightcyan': '#00ffff',
            'brightwhite': '#ffffff',
        }
        if isinstance(color, str):
            return color_map.get(color.lower(), color)
        elif isinstance(color, tuple) and len(color) == 3:
            return f'#{color[0]:02x}{color[1]:02x}{color[2]:02x}'
        return None
    
    def get_cursor_position(self):
        return (self.screen.cursor.x, self.screen.cursor.y)
    
    def clear(self):
        self.screen.reset()
        
    def resize(self, columns, rows):
        self.columns = columns
        self.rows = rows
        self.screen.resize(columns, rows)


class PortComboBox(ComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._port_data = []

    def addPortItems(self, port_infos):
        self._port_data = port_infos
        self.clear()
        for port_info in port_infos:
            self.addItem(port_info)

    def getPortData(self, index):
        if 0 <= index < len(self._port_data):
            return self._port_data[index]
        return ""

    def currentPortData(self):
        return self.getPortData(self.currentIndex())

    def setCurrentPortByDevice(self, device):
        for i, port_info in enumerate(self._port_data):
            if port_info.startswith(device):
                self.setCurrentIndex(i)
                return True
        return False

    def currentText(self):
        port_data = self.currentPortData()
        return port_data.split(" : ")[0] if " : " in port_data else port_data


class TerminalTextEdit(PlainTextEdit):
    send_data = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._terminal_mode = False
        self._use_pyte = True
        self._pyte_terminal = PyteTerminal(columns=120, rows=1000)
        self._setup_font()
        self._setup_document()

    def _setup_font(self):
        font = QFont("FiraMono Nerd Font", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias | QFont.StyleStrategy.PreferQuality)
        self.setFont(font)

    def _setup_document(self):
        doc = self.document()
        doc.setDocumentMargin(2)

    def set_terminal_mode(self, enabled):
        self._terminal_mode = enabled
        if enabled:
            cursor = self.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.setTextCursor(cursor)
            self.setCursorWidth(self.fontMetrics().averageCharWidth())
        else:
            self.setCursorWidth(1)

    def set_pyte_mode(self, enabled):
        self._use_pyte = enabled
        if enabled:
            self._pyte_terminal.clear()

    def feed_data(self, data):
        if self._use_pyte and self._terminal_mode:
            self._pyte_terminal.feed(data)
            self._update_display()
        else:
            cursor = self.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.insertText(data)
            self.setTextCursor(cursor)
            self.ensureCursorVisible()

    def _update_display(self):
        self.setPlainText(self._pyte_terminal.get_display())
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.setTextCursor(cursor)

    def clear_terminal(self):
        if self._use_pyte:
            self._pyte_terminal.clear()
        self.clear()

    def paintEvent(self, event):
        super().paintEvent(event)
        if hasattr(self, '_theme'):
            if self._theme == Theme.DARK:
                self.setStyleSheet("background-color: #1e1e1e; color: #ffffff;")
            else:
                self.setStyleSheet("background-color: #ffffff; color: #000000;")

    def set_theme(self, theme):
        self._theme = theme
        self.paintEvent(None)

    def keyPressEvent(self, event: QKeyEvent):
        if self._terminal_mode:
            if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
                self.send_data.emit("\r")
                return
            elif event.key() == Qt.Key.Key_Backspace:
                self.send_data.emit("\x7f")
                return
            elif event.key() == Qt.Key.Key_Delete:
                self.send_data.emit("\x7f")
                return
            text = event.text()
            if text:
                self.send_data.emit(text)
                return
        super().keyPressEvent(event)


class SendTextEdit(PlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._history = []
        self._history_index = -1
        self._current_text_before_history = ""

    def add_to_history(self, text):
        if text and text.strip():
            if self._history and self._history[-1] == text:
                return
            self._history.append(text)
            if len(self._history) > 100:
                self._history.pop(0)
            self._history_index = len(self._history)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Up:
            if self._history:
                if self._history_index == len(self._history):
                    self._current_text_before_history = self.toPlainText()
                if self._history_index > 0:
                    self._history_index -= 1
                    self.setPlainText(self._history[self._history_index])
                    cursor = self.textCursor()
                    cursor.movePosition(QTextCursor.MoveOperation.End)
                    self.setTextCursor(cursor)
            return
        elif event.key() == Qt.Key.Key_Down:
            if self._history:
                if self._history_index < len(self._history) - 1:
                    self._history_index += 1
                    self.setPlainText(self._history[self._history_index])
                else:
                    self._history_index = len(self._history)
                    self.setPlainText(self._current_text_before_history)
                cursor = self.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.End)
                self.setTextCursor(cursor)
            return
        super().keyPressEvent(event)


class Serial_Data_Reader_Thread(QThread):
    data_received = pyqtSignal(str)
    raw_data_received = pyqtSignal(bytes)
    hex_data_received = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, serial_port):
        super().__init__()
        self.serial_port = serial_port
        self.running = True
        self._text_buffer = ""
        self._raw_buffer = b""
        self._hex_buffer = ""
        self._buffer_timer = QTimer()
        self._buffer_timer.timeout.connect(self._flush_buffer)
        self._buffer_timer.start(50)
        print("Serial_Data_Reader_Thread 初始化完成")

    def _flush_buffer(self):
        if self._text_buffer:
            self.data_received.emit(self._text_buffer)
            self._text_buffer = ""
        if self._raw_buffer:
            self.raw_data_received.emit(self._raw_buffer)
            self._raw_buffer = b""
        if self._hex_buffer:
            self.hex_data_received.emit(self._hex_buffer)
            self._hex_buffer = ""

    def run(self):
        print("Serial_Data_Reader_Thread 开始运行")
        while self.running:
            if self.serial_port is None or not self.serial_port.isOpen():
                print("串口未打开或已关闭，停止读取数据")
                break
            try:
                if self.serial_port.in_waiting > 0:
                    data = self.serial_port.read(self.serial_port.in_waiting)
                    self._raw_buffer += data
                    decoded_text = data.decode('utf-8', errors='replace')
                    decoded_text = decoded_text.replace('\r\n', '\n').replace('\r', '\n')
                    self._text_buffer += decoded_text
                    hex_data = data.hex()
                    if hex_data:
                        formatted_hex = " ".join(
                            [hex_data[i : i + 2] for i in range(0, len(hex_data), 2)]
                        )
                        self._hex_buffer += formatted_hex + " "

            except SerialException as e:
                print(f"读取数据失败: {e}")
                self.error_occurred.emit(f"读取数据失败: {e}")
                break
            except Exception as e:
                print(f"未知错误: {e}")
                self.error_occurred.emit(f"未知错误: {e}")
                break

            self.msleep(10)

        self._flush_buffer()
        print("Serial_Data_Reader_Thread 结束运行")

    def stop(self):
        self.running = False
        self._buffer_timer.stop()
        if self.serial_port is not None:
            self.serial_port.close()
            self.serial_port = None
        self.wait()  # 等待线程结束


class YModem_Send_Thread(QThread):
    progress_updated = pyqtSignal(int, str, int, int)
    send_completed = pyqtSignal(bool, str)

    def __init__(self, serial_port, file_paths):
        super().__init__()
        self.serial_port = serial_port
        self.file_paths = file_paths

    def run(self):
        def read(size, timeout=3):
            try:
                data = self.serial_port.read(size)
                return data
            except Exception as e:
                return b''

        def write(data, timeout=3):
            try:
                self.serial_port.write(data)
                return len(data)
            except Exception as e:
                return 0

        def ymodem_callback(task_index, task_name, total_packets, success_packets):
            self.progress_updated.emit(task_index, task_name, total_packets, success_packets)

        try:
            from ymodem.Socket import ModemSocket
            cli = ModemSocket(read, write)
            result = cli.send(self.file_paths, callback=ymodem_callback)
            if result:
                self.send_completed.emit(True, f"已成功发送 {len(self.file_paths)} 个文件")
            else:
                self.send_completed.emit(False, "文件发送过程中出现错误")
        except Exception as e:
            self.send_completed.emit(False, str(e))


class Serial_Tools_Widget(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("serial_setting_widget")
        self.resize(1000, 700)
        self.pivot = SegmentedWidget(self)
        self.stackedWidget = QStackedWidget(self)
        self.Main_hLayout = QHBoxLayout(self)
        self.serial_setting_vBoxLayout = QVBoxLayout()
        self.serial_setting = QWidget()
        self.more_setting = QWidget()
        self.add_sub_interface(self.serial_setting, "serial_setting", "串口设置")
        self.add_sub_interface(self.more_setting, "more_setting", "更多设置")

        self.serial_setting_vBoxLayout.addWidget(self.pivot)
        self.serial_setting_vBoxLayout.addWidget(self.stackedWidget)
        self.serial_setting_vBoxLayout.addStretch(1)
        self.Main_hLayout.addLayout(self.serial_setting_vBoxLayout)
        self.init_receive_bar_ui()
        self.init_send_bar_ui()
        self.stackedWidget.setCurrentWidget(self.serial_setting)
        self.pivot.setCurrentItem("serial_setting")
        self.pivot.currentItemChanged.connect(self._on_pivot_changed)
        self.init_serial_setting_ui()
        self.init_more_setting_ui()

        self.serial_poll_timer = QTimer(self)
        self.serial_poll_timer.timeout.connect(self.check_serial_ports)
        self.serial_poll_timer.start(200)

        self.current_ports = []
        self._is_first_load = True
        self.parity_mapping = {
            "无": "N",
            "偶": "E",
            "奇": "O",
            "标记": "M",
            "空格": "S",
        }
        self.serial_port = None
        self.serial_text_buffer = bytearray()
        self.serial_hex_buffer = bytearray()
        
        self._load_config()
        self._update_left_panel_width()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, '_opacity_effect') and self._opacity_effect:
            self._refresh_opacity_effect()

    def _on_pivot_changed(self, key):
        self.stackedWidget.setCurrentWidget(self.findChild(QWidget, key))
        if self.stackedWidget.currentWidget() == self.more_setting:
            self.more_setting.hide()
        QTimer.singleShot(250, self._update_left_panel_width)

    def _update_left_panel_width(self):
        current_widget = self.stackedWidget.currentWidget()
        if current_widget == self.serial_setting:
            target_width = 185
        else:
            target_width = 260

        current_width = self.stackedWidget.width()

        if not hasattr(self, '_min_width_animation'):
            self._min_width_animation = QPropertyAnimation(self.stackedWidget, b"minimumWidth")
            self._min_width_animation.setDuration(200)
            self._min_width_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
            
            self._max_width_animation = QPropertyAnimation(self.stackedWidget, b"maximumWidth")
            self._max_width_animation.setDuration(200)
            self._max_width_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
            self._max_width_animation.finished.connect(self._on_animation_finished)

        self._min_width_animation.stop()
        self._max_width_animation.stop()
        
        self._min_width_animation.setStartValue(current_width)
        self._min_width_animation.setEndValue(target_width)
        self._max_width_animation.setStartValue(current_width)
        self._max_width_animation.setEndValue(target_width)
        
        self._min_width_animation.start()
        self._max_width_animation.start()

    def _on_animation_finished(self):
        current_widget = self.stackedWidget.currentWidget()
        if current_widget == self.more_setting:
            self._start_fade_in_animation()

    def _start_fade_in_animation(self):
        if not hasattr(self, '_opacity_effect'):
            self._opacity_effect = QGraphicsOpacityEffect(self.more_setting)
            self.more_setting.setGraphicsEffect(self._opacity_effect)
            
            self._fade_animation = QPropertyAnimation(self._opacity_effect, b"opacity")
            self._fade_animation.setDuration(150)
            self._fade_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        
        self._opacity_effect.setOpacity(0)
        self.more_setting.show()
        
        self._fade_animation.stop()
        self._fade_animation.setStartValue(0)
        self._fade_animation.setEndValue(1)
        self._fade_animation.start()

    def _refresh_opacity_effect(self):
        if hasattr(self, '_opacity_effect') and self._opacity_effect:
            if self.stackedWidget.currentWidget() == self.more_setting:
                current_opacity = self._opacity_effect.opacity()
                has_animation = hasattr(self, '_fade_animation')
                if has_animation:
                    self._fade_animation.stop()
                self.more_setting.setGraphicsEffect(None)
                self._opacity_effect = QGraphicsOpacityEffect(self.more_setting)
                self._opacity_effect.setOpacity(current_opacity)
                self.more_setting.setGraphicsEffect(self._opacity_effect)
                if has_animation:
                    self._fade_animation.setTargetObject(self._opacity_effect)

    def init_receive_bar_ui(self):
        self.right_vBoxLayout = QVBoxLayout()
        self.right_vBoxLayout.setSpacing(0)
        self.right_vBoxLayout.setContentsMargins(0, 0, 0, 0)

        self.receive_bar_widget = QWidget()
        self.receive_bar_vBoxLayout = QVBoxLayout(self.receive_bar_widget)

        self.reception_area_text_hLayout = QHBoxLayout()

        self.reception_area_text = TerminalTextEdit()
        self.reception_area_text_hLayout.addWidget(self.reception_area_text)
        self.reception_area_text.setReadOnly(False)
        self.reception_area_text.set_terminal_mode(True)
        self.reception_area_text.send_data.connect(self.send_terminal_data)
        self._text_cleared = False
        self._hex_cleared = False
        self.reception_area_Hex_text = PlainTextEdit()
        font = QFont("FiraMono Nerd Font", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias | QFont.StyleStrategy.PreferQuality)
        self.reception_area_Hex_text.setFont(font)
        self.reception_area_text_hLayout.addWidget(self.reception_area_Hex_text)
        self.reception_area_Hex_text.setReadOnly(True)
        self.reception_area_Hex_text.hide()

        self.receive_bar_vBoxLayout.addLayout(self.reception_area_text_hLayout)

        self.receive_bar_button_hLayout = QHBoxLayout()

        self.receive_bar_edit_togglebutton = ToggleButton("终端模式", self)
        self.receive_bar_edit_togglebutton.setIcon(FIF.COMMAND_PROMPT)
        self.receive_bar_edit_togglebutton.setMaximumWidth(120)
        self.receive_bar_edit_togglebutton.setChecked(True)
        self.receive_bar_edit_togglebutton.toggled.connect(
            self.onToggle_receive_bar_edit_togglebutton
        )
        self.receive_bar_button_hLayout.addWidget(self.receive_bar_edit_togglebutton)

        self.receive_bar_clear_button = DropDownPushButton(
            FIF.DELETE, "清空接收区", self
        )
        self.menu = RoundMenu(parent=self)
        clear_text_action = QAction("清空文本区")
        clear_Hex_action = QAction("清空Hex区")
        clear_receive_action = QAction("清空接收区")
        clear_text_action.triggered.connect(self.on_text_clicked)
        clear_Hex_action.triggered.connect(self.on_Hex_clicked)
        clear_receive_action.triggered.connect(self.on_receive_clicked)
        self.menu.addAction(clear_text_action)
        self.menu.addAction(clear_Hex_action)
        self.menu.addAction(clear_receive_action)
        self.receive_bar_clear_button.setMenu(self.menu)
        self.receive_bar_button_hLayout.addWidget(self.receive_bar_clear_button)

        self.reception_area_fontsize_spinBox = SpinBox()
        self.reception_area_fontsize_spinBox.setRange(4, 100)
        self.reception_area_fontsize_spinBox.setValue(10)
        self.reception_area_fontsize_spinBox.valueChanged.connect(
            self.change_reception_area_fontsize
        )
        self.receive_bar_button_hLayout.addWidget(self.reception_area_fontsize_spinBox)

        self.receive_bar_button_hLayout.addStretch(1)

        self.export_button = DropDownPushButton(FIF.SAVE, "导出", self)
        self.export_button.setFixedWidth(105)
        self.export_menu = RoundMenu(parent=self)
        export_text_action = QAction("导出文本区")
        export_hex_action = QAction("导出Hex区")
        export_text_action.triggered.connect(lambda: self.on_export_clicked("text"))
        export_hex_action.triggered.connect(lambda: self.on_export_clicked("hex"))
        self.export_menu.addAction(export_text_action)
        self.export_menu.addAction(export_hex_action)
        self.export_button.setMenu(self.export_menu)
        self.receive_bar_button_hLayout.addWidget(self.export_button)

        self.receive_bar_vBoxLayout.addLayout(self.receive_bar_button_hLayout)
        self.receive_bar_vBoxLayout.setSpacing(10)
        self.receive_bar_vBoxLayout.setContentsMargins(0, 0, 0, 9)

        self.right_vBoxLayout.addWidget(self.receive_bar_widget, 5)
        self.Main_hLayout.addLayout(self.right_vBoxLayout, 1)

    def init_send_bar_ui(self):
        self.send_bar_widget = QWidget()
        self.send_bar_vBoxLayout = QVBoxLayout(self.send_bar_widget)

        # 创建发送区的水平布局，左侧放置进度环，右侧放置文本编辑区
        send_area_hLayout = QHBoxLayout()
        
        # 初始化进度环
        self.ymodem_progress_ring = ProgressRing(self)
        # 增加进度环的大小
        self.ymodem_progress_ring.setFixedSize(150, 150)
        self.ymodem_progress_ring.setValue(0)
        self.ymodem_progress_ring.setTextVisible(True)
        self.ymodem_progress_ring.hide()
        
        # 发送文本区
        self.send_area_text = SendTextEdit()
        self.send_area_text.setReadOnly(False)
        font = QFont("Microsoft YaHei", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias | QFont.StyleStrategy.PreferQuality)
        self.send_area_text.setFont(font)
        
        # 将进度环添加到左侧，设置垂直对齐方式为居中
        send_area_hLayout.addWidget(self.ymodem_progress_ring, 0, Qt.AlignmentFlag.AlignVCenter)
        send_area_hLayout.addWidget(self.send_area_text, 1)
        
        self.send_bar_vBoxLayout.addLayout(send_area_hLayout)

        self._send_hex_mode = False

        self.send_bar_button_hLayout = QHBoxLayout()

        self.send_format_combo = ComboBox()
        self.send_format_combo.addItems(["文本发送", "Hex发送"])
        self.send_format_combo.setCurrentIndex(0)
        self.send_format_combo.setFixedWidth(100)
        self.send_format_combo.currentIndexChanged.connect(self.on_send_format_changed)
        self.send_bar_button_hLayout.addWidget(self.send_format_combo)

        self.send_bar_clear_button = PushButton(FIF.DELETE, "清空", self)
        self.send_bar_clear_button.clicked.connect(self.clear_send_area)
        self.send_bar_button_hLayout.addWidget(self.send_bar_clear_button)

        self.auto_clear_checkbox = CheckBox("自动清除", self)
        self.auto_clear_checkbox.setChecked(False)
        self.send_bar_button_hLayout.addWidget(self.auto_clear_checkbox)

        self.send_area_fontsize_spinBox = SpinBox()
        self.send_area_fontsize_spinBox.setRange(4, 100)
        self.send_area_fontsize_spinBox.setValue(cfg.get(cfg.serialSendFontSize))
        self.send_area_fontsize_spinBox.valueChanged.connect(
            self.change_send_area_fontsize
        )
        self.send_bar_button_hLayout.addWidget(self.send_area_fontsize_spinBox)

        self.send_bar_button_hLayout.addStretch(1)

        self.ymodem_send_button = PushButton(FIF.FOLDER, "YMODEM发送", self)
        self.ymodem_send_button.setFixedWidth(150)
        self.ymodem_send_button.clicked.connect(self.on_ymodem_send_clicked)
        self.send_bar_button_hLayout.addWidget(self.ymodem_send_button)

        self.send_button = PushButton(FIF.SEND, "发送", self)
        self.send_button.setFixedWidth(105)
        self.send_button.clicked.connect(self.on_send_clicked)
        self.send_bar_button_hLayout.addWidget(self.send_button)

        self.send_bar_vBoxLayout.addLayout(self.send_bar_button_hLayout)
        self.send_bar_vBoxLayout.setSpacing(10)
        self.send_bar_vBoxLayout.setContentsMargins(0, 0, 0, 9)

        self.right_vBoxLayout.addWidget(self.send_bar_widget, 2)
        self.send_bar_widget.hide()

        self._send_bar_max_height = 0
        self._setup_send_animation()

    def _setup_send_animation(self):
        self._send_bar_height_animation = QPropertyAnimation(self.send_bar_widget, b"maximumHeight")
        self._send_bar_height_animation.setDuration(200)
        self._send_bar_height_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._send_bar_height_animation.finished.connect(self._on_height_animation_finished)

        self._send_bar_min_height_animation = QPropertyAnimation(self.send_bar_widget, b"minimumHeight")
        self._send_bar_min_height_animation.setDuration(200)
        self._send_bar_min_height_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)

        self._send_bar_opacity_effect = QGraphicsOpacityEffect(self.send_bar_widget)
        self.send_bar_widget.setGraphicsEffect(self._send_bar_opacity_effect)
        self._send_bar_opacity_effect.setOpacity(0)

        self._send_bar_opacity_animation = QPropertyAnimation(self._send_bar_opacity_effect, b"opacity")
        self._send_bar_opacity_animation.setDuration(200)
        self._send_bar_opacity_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)

    def _on_height_animation_finished(self):
        if self.send_bar_widget.maximumHeight() == 0:
            self.send_bar_widget.hide()
        else:
            # 当发送区显示完成后，使接收区下滑到底部
            cursor = self.reception_area_text.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.reception_area_text.setTextCursor(cursor)
            self.reception_area_text.ensureCursorVisible()
            # 同时处理Hex显示区
            cursor_hex = self.reception_area_Hex_text.textCursor()
            cursor_hex.movePosition(QTextCursor.MoveOperation.End)
            self.reception_area_Hex_text.setTextCursor(cursor_hex)
            self.reception_area_Hex_text.ensureCursorVisible()

    def _show_send_bar_with_animation(self):
        self.send_bar_widget.show()
        self.send_bar_widget.setMaximumHeight(16777215)
        
        self.send_bar_widget.ensurePolished()
        self._send_bar_max_height = self.send_bar_widget.sizeHint().height()
        
        self._send_bar_height_animation.stop()
        self._send_bar_min_height_animation.stop()
        self._send_bar_opacity_animation.stop()
        
        self.send_bar_widget.setMaximumHeight(0)
        self.send_bar_widget.setMinimumHeight(0)
        
        self._send_bar_height_animation.setStartValue(0)
        self._send_bar_height_animation.setEndValue(self._send_bar_max_height)
        self._send_bar_min_height_animation.setStartValue(0)
        self._send_bar_min_height_animation.setEndValue(self._send_bar_max_height)
        self._send_bar_opacity_animation.setStartValue(0)
        self._send_bar_opacity_animation.setEndValue(1)
        
        self._send_bar_height_animation.start()
        self._send_bar_min_height_animation.start()
        self._send_bar_opacity_animation.start()

    def _hide_send_bar_with_animation(self):
        current_height = self.send_bar_widget.height()
        
        self._send_bar_height_animation.stop()
        self._send_bar_min_height_animation.stop()
        self._send_bar_opacity_animation.stop()
        
        self._send_bar_height_animation.setStartValue(current_height)
        self._send_bar_height_animation.setEndValue(0)
        self._send_bar_min_height_animation.setStartValue(current_height)
        self._send_bar_min_height_animation.setEndValue(0)
        self._send_bar_opacity_animation.setStartValue(1)
        self._send_bar_opacity_animation.setEndValue(0)
        
        self._send_bar_height_animation.start()
        self._send_bar_min_height_animation.start()
        self._send_bar_opacity_animation.start()

    def init_serial_setting_ui(self):
        main_serial_setting_layout = QVBoxLayout()
        # Port selection
        port_label = BodyLabel("端口号:")
        self.port_combo = PortComboBox()
        self.port_combo.setObjectName("port_combo")
        self.port_combo.addPortItems(self.get_serial_ports())
        self.port_combo.currentIndexChanged.connect(
            lambda index: self.on_combobox_changed(self.port_combo, "端口号")
        )

        port_hlayout = QHBoxLayout()
        port_hlayout.addWidget(port_label)
        port_hlayout.addStretch(1)
        port_hlayout.addWidget(self.port_combo)
        self.port_combo.setFixedWidth(90)
        main_serial_setting_layout.addLayout(port_hlayout)

        # Baudrate selection
        baudrate_label = BodyLabel("波特率:")
        self.baudrate_combo = ComboBox()
        self.baudrate_combo.setObjectName("baudrate_combo")
        baudrates = [
            "2400",
            "4800",
            "9600",
            "19200",
            "38400",
            "57600",
            "115200",
            "230400",
            "460800",
            "576000",
            "921600",
            "1152000",
        ]
        self.baudrate_combo.addItems(baudrates)
        self.baudrate_combo.setCurrentIndex(6)
        self.baudrate_combo.currentTextChanged.connect(
            lambda text: self.on_combobox_changed(self.baudrate_combo, "波特率")
        )

        baudrate_hlayout = QHBoxLayout()
        baudrate_hlayout.addWidget(baudrate_label)
        baudrate_hlayout.addStretch(1)
        baudrate_hlayout.addWidget(self.baudrate_combo)
        self.baudrate_combo.setFixedWidth(90)
        main_serial_setting_layout.addLayout(baudrate_hlayout)

        # Data bits selection
        databit_label = BodyLabel("数据位:")
        self.databit_combo = ComboBox()
        self.databit_combo.setObjectName("databit_combo")
        databits = ["5", "6", "7", "8"]
        self.databit_combo.addItems(databits)
        self.databit_combo.setCurrentIndex(3)
        self.databit_combo.currentTextChanged.connect(
            lambda text: self.on_combobox_changed(self.databit_combo, "数据位")
        )

        databit_hlayout = QHBoxLayout()
        databit_hlayout.addWidget(databit_label)
        databit_hlayout.addStretch(1)
        databit_hlayout.addWidget(self.databit_combo)
        self.databit_combo.setFixedWidth(90)
        main_serial_setting_layout.addLayout(databit_hlayout)

        # Stop bits selection
        stopbit_label = BodyLabel("停止位:")
        self.stopbit_combo = ComboBox()
        self.stopbit_combo.setObjectName("stopbit_combo")
        stopbits = ["1", "1.5", "2"]
        self.stopbit_combo.addItems(stopbits)
        self.stopbit_combo.currentTextChanged.connect(
            lambda text: self.on_combobox_changed(self.stopbit_combo, "停止位")
        )

        stopbit_hlayout = QHBoxLayout()
        stopbit_hlayout.addWidget(stopbit_label)
        stopbit_hlayout.addStretch(1)
        stopbit_hlayout.addWidget(self.stopbit_combo)
        self.stopbit_combo.setFixedWidth(90)
        main_serial_setting_layout.addLayout(stopbit_hlayout)

        # Parity selection
        parity_label = BodyLabel("奇偶校验:")
        self.parity_combo = ComboBox()
        self.parity_combo.setObjectName("parity_combo")
        parities = ["无", "偶校验", "奇校验", "标记", "空格"]
        self.parity_combo.addItems(parities)
        self.parity_combo.currentTextChanged.connect(
            lambda text: self.on_combobox_changed(self.parity_combo, "奇偶校验")
        )

        parity_hlayout = QHBoxLayout()
        parity_hlayout.addWidget(parity_label)
        parity_hlayout.addStretch(1)
        parity_hlayout.addWidget(self.parity_combo)
        self.parity_combo.setFixedWidth(90)
        main_serial_setting_layout.addLayout(parity_hlayout)

        dtr_rts_hlayout = QHBoxLayout()
        self.dtr_switch = TogglePushButton("DTR", self)
        self.dtr_switch.setChecked(cfg.get(cfg.serialDtrState))
        self.dtr_switch.toggled.connect(self.on_dtr_changed)
        dtr_rts_hlayout.addWidget(self.dtr_switch)

        self.rts_switch = TogglePushButton("RTS", self)
        self.rts_switch.setChecked(cfg.get(cfg.serialRtsState))
        self.rts_switch.toggled.connect(self.on_rts_changed)
        dtr_rts_hlayout.addWidget(self.rts_switch)
        main_serial_setting_layout.addLayout(dtr_rts_hlayout)

        self.serial_start_pushbutton = ToggleButton(FIF.PLAY_SOLID, "开始监视", self)
        self.serial_start_pushbutton.toggled.connect(
            self.onToggle_serial_start_pushbutton
        )
        serial_port_start_hlayout = QHBoxLayout()
        serial_port_start_hlayout.addWidget(self.serial_start_pushbutton)
        main_serial_setting_layout.addLayout(serial_port_start_hlayout)

        self.textMode_checkBox = CheckBox("文本显示区", self)
        self.textMode_checkBox.setChecked(True)
        main_serial_setting_layout.addWidget(self.textMode_checkBox)

        self.HexMode_checkBox = CheckBox("Hex显示区", self)
        main_serial_setting_layout.addWidget(self.HexMode_checkBox)

        self.timestamp_checkBox = CheckBox("时间戳", self)
        self.timestamp_checkBox.setChecked(False)
        main_serial_setting_layout.addWidget(self.timestamp_checkBox)

        self.textMode_checkBox.stateChanged.connect(self.update_checkBox_state)
        self.HexMode_checkBox.stateChanged.connect(self.update_checkBox_state)

        main_serial_setting_layout.setSpacing(12)
        self.serial_setting.setLayout(main_serial_setting_layout)

    def init_more_setting_ui(self):
        more_setting_layout = QVBoxLayout()
        
        font_group_label = StrongBodyLabel("字体设置")
        more_setting_layout.addWidget(font_group_label)
        
        font_hlayout = QHBoxLayout()
        self.font_display_label = BodyLabel(cfg.get(cfg.serialFontFamily))
        self.font_display_label.setMinimumWidth(150)
        self.font_select_button = PushButton(FIF.FONT, "选择字体", self)
        self.font_select_button.clicked.connect(self.on_font_select_clicked)
        font_hlayout.addStretch(1)
        font_hlayout.addWidget(self.font_display_label)
        font_hlayout.addWidget(self.font_select_button)
        font_hlayout.addStretch(1)
        more_setting_layout.addLayout(font_hlayout)
        
        more_setting_layout.addStretch(1)
        self.more_setting.setLayout(more_setting_layout)

    def _load_config(self):
        font = cfg.serialFont
        self.reception_area_text.setFont(font)
        self.reception_area_Hex_text.setFont(font)
        self.reception_area_fontsize_spinBox.setValue(cfg.get(cfg.serialFontSize))
        
        send_font = QFont("Microsoft YaHei", cfg.get(cfg.serialSendFontSize))
        send_font.setStyleHint(QFont.StyleHint.Monospace)
        send_font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
        send_font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias | QFont.StyleStrategy.PreferQuality)
        self.send_area_text.setFont(send_font)
        self.send_area_fontsize_spinBox.setValue(cfg.get(cfg.serialSendFontSize))

    def on_dtr_changed(self, checked):
        cfg.set(cfg.serialDtrState, checked)
        if self.serial_port is not None and self.serial_port.is_open:
            self.serial_port.dtr = checked
        state = "开启" if checked else "关闭"
        self.show_success_info_bar("DTR状态：", f"已{state}", 1000)

    def on_rts_changed(self, checked):
        cfg.set(cfg.serialRtsState, checked)
        if self.serial_port is not None and self.serial_port.is_open:
            self.serial_port.rts = checked
        state = "开启" if checked else "关闭"
        self.show_success_info_bar("RTS状态：", f"已{state}", 1000)

    def on_font_select_clicked(self):
        font, ok = QFontDialog.getFont(cfg.serialFont, self, "选择串口文本字体")
        if ok:
            cfg.serialFont = font
            self.font_display_label.setText(font.family())
            self.reception_area_text.setFont(font)
            self.reception_area_Hex_text.setFont(font)
            self.reception_area_fontsize_spinBox.setValue(font.pointSize())
            
            send_font = QFont("Microsoft YaHei", cfg.get(cfg.serialSendFontSize))
            send_font.setStyleHint(QFont.StyleHint.Monospace)
            send_font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
            send_font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias | QFont.StyleStrategy.PreferQuality)
            self.send_area_text.setFont(send_font)
            self.show_success_info_bar("字体设置：", f"已设置为 {font.family()}", 1000)

    def update_checkBox_state(self, state=None):
        # 当前被触发的复选框
        sender = self.sender()
        # 如果发送者是文本模式复选框并且没有被选中，则选中Hex模式复选框
        if sender == self.textMode_checkBox and not self.textMode_checkBox.isChecked():
            self.HexMode_checkBox.setChecked(True)
            self.reception_area_Hex_text.show()
            self.reception_area_text.hide()
        # 如果发送者是Hex模式复选框并且没有被选中，则选中文本模式复选框
        elif sender == self.HexMode_checkBox and not self.HexMode_checkBox.isChecked():
            self.textMode_checkBox.setChecked(True)
            self.reception_area_text.show()
            self.reception_area_Hex_text.hide()
        else:
            self.reception_area_text.show()
            self.reception_area_Hex_text.show()

    def change_reception_area_fontsize(self, value):
        font = cfg.serialFont
        font.setPointSize(value)
        cfg.serialFont = font
        self.reception_area_text.setFont(font)
        self.reception_area_Hex_text.setFont(font)

    def onToggle_receive_bar_edit_togglebutton(self, checked):
        if checked:
            self.reception_area_text.setReadOnly(False)
            self.reception_area_Hex_text.setReadOnly(False)
            self.reception_area_text.set_terminal_mode(True)
            self.receive_bar_edit_togglebutton.setText("关闭终端")
            self.receive_bar_edit_togglebutton.setIcon(FIF.CLOSE)
            self._hide_send_bar_with_animation()
            # 自动对焦到接收区
            self.reception_area_text.setFocus()
            self.reception_area_text.activateWindow()
            self.show_success_info_bar("终端模式：", "已开启，可交互发送数据", 1000)
        else:
            self.reception_area_text.setReadOnly(True)
            self.reception_area_Hex_text.setReadOnly(True)
            self.reception_area_text.set_terminal_mode(False)
            self.receive_bar_edit_togglebutton.setText("终端模式")
            self.receive_bar_edit_togglebutton.setIcon(FIF.COMMAND_PROMPT)
            self._show_send_bar_with_animation()
            # 使接收区下滑到底部
            cursor = self.reception_area_text.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.reception_area_text.setTextCursor(cursor)
            self.reception_area_text.ensureCursorVisible()
            # 同时处理Hex显示区
            cursor_hex = self.reception_area_Hex_text.textCursor()
            cursor_hex.movePosition(QTextCursor.MoveOperation.End)
            self.reception_area_Hex_text.setTextCursor(cursor_hex)
            self.reception_area_Hex_text.ensureCursorVisible()
            self.show_success_info_bar("终端模式：", "已关闭", 1000)

    def send_terminal_data(self, data):
        if self.serial_port is not None and self.serial_port.is_open:
            try:
                self.serial_port.write(data.encode('latin-1'))
            except Exception as e:
                InfoBar.error(
                    title="发送失败：",
                    content=str(e),
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=3000,
                    parent=self,
                )

    def on_text_clicked(self):
        self.reception_area_text.clear_terminal()
        self._text_cleared = False
        self.show_success_info_bar("接收栏：", "已清空文本区", 1000)

    def on_Hex_clicked(self):
        self.reception_area_Hex_text.clear()
        self._hex_cleared = False
        self.show_success_info_bar("接收栏：", "已清空Hex区", 1000)

    def on_receive_clicked(self):
        self.reception_area_text.clear_terminal()
        self.reception_area_Hex_text.clear()
        self._text_cleared = False
        self._hex_cleared = False
        self.show_success_info_bar("接收栏：", "已清空接收区", 1000)

    def _enable_serial_settings(self, enabled):
        self.port_combo.setEnabled(enabled)
        self.baudrate_combo.setEnabled(enabled)
        self.databit_combo.setEnabled(enabled)
        self.stopbit_combo.setEnabled(enabled)
        self.parity_combo.setEnabled(enabled)
        self.dtr_switch.setEnabled(enabled)
        self.rts_switch.setEnabled(enabled)

    def onToggle_serial_start_pushbutton(self, checked):
        def reset_button_and_close_serial():
            self.serial_start_pushbutton.setText("开始监视")
            self.serial_start_pushbutton.setIcon(FIF.PLAY_SOLID)
            if self.serial_port is not None:
                self.serial_port.close()
                self.serial_port = None
                # 只有在data_read_thread存在时才尝试停止它
                if (
                    hasattr(self, "data_read_thread")
                    and self.data_read_thread is not None
                ):
                    self.data_read_thread.stop()
                    self.data_read_thread.wait()  # 确保线程结束
                    self.data_read_thread = None  # 清除对线程的引用
                    current_port_text = self.port_combo.currentText()
                    InfoBar.info(
                        title="串口已断开连接:",
                        content=f"串口-{current_port_text}",
                        orient=Qt.Orientation.Horizontal,
                        isClosable=True,
                        position=InfoBarPosition.TOP,
                        duration=2000,
                        parent=self,
                    )
            # 启用串口设置控件
            self._enable_serial_settings(True)

        if checked:
            current_port_text = self.port_combo.currentText()
            if not current_port_text:
                InfoBar.warning(
                    title="当前串口号为空:",
                    content="请先连接或选择一个有效的串口",
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=2000,
                    parent=self,
                )
                self.serial_start_pushbutton.setChecked(False)
                return

            # 禁用串口设置控件
            self._enable_serial_settings(False)
            
            self.serial_start_pushbutton.setText("结束监视")
            self.serial_start_pushbutton.setIcon(FIF.PAUSE_BOLD)
            parity_to_char = self.parity_mapping.get(
                self.parity_combo.currentText(), "N"
            )
            try:
                self.serial_port = Serial(
                    port=current_port_text,
                    baudrate=int(self.baudrate_combo.currentText()),
                    bytesize=int(self.databit_combo.currentText()),
                    parity=parity_to_char,
                    timeout=0.1,
                    stopbits=float(self.stopbit_combo.currentText()),
                )
                self.serial_port.dtr = self.dtr_switch.isChecked()
                self.serial_port.rts = self.rts_switch.isChecked()
                self.data_read_thread = Serial_Data_Reader_Thread(
                    self.serial_port
                )
                self.data_read_thread.data_received.connect(
                    self.on_text_data_received
                )
                self.data_read_thread.raw_data_received.connect(
                    self.on_raw_data_received
                )
                self.data_read_thread.hex_data_received.connect(
                    self.on_hex_data_received
                )
                self.data_read_thread.start()
                InfoBar.success(
                    title="串口已成功连接:",
                    content=f"串口-{current_port_text.split(':')[0]}",
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=2000,
                    parent=self,
                )
                self.reception_area_text.setFocus()
                self.reception_area_text.activateWindow()
            except Exception as e:
                print(f"串口打开失败: {e}")
                InfoBar.error(
                    title="串口连接失败:",
                    content="当前串口已被占用或不可用",
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.BOTTOM_RIGHT,
                    duration=15000,
                    parent=self,
                )
                self.serial_start_pushbutton.setChecked(False)
                # 重新启用串口设置控件
                self._enable_serial_settings(True)
                reset_button_and_close_serial()
        else:
            # 断开信号连接
            if hasattr(self, "data_read_thread") and self.data_read_thread is not None:
                try:
                    self.data_read_thread.hex_data_received.disconnect(
                        self.on_hex_data_received
                    )
                except TypeError:
                    pass
            reset_button_and_close_serial()

    def on_text_data_received(self, text_data):
        if self.reception_area_text._terminal_mode:
            return
        
        if not self._text_cleared:
            self.reception_area_text.clear()
            self._text_cleared = True
        
        display_text = text_data
        if self.timestamp_checkBox.isChecked():
            now = datetime.now()
            timestamp = now.strftime("%H:%M:%S.") + f"{now.microsecond // 1000:03d}"
            display_text = f"[{timestamp}] {text_data}"
        
        cursor = self.reception_area_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(display_text)
        self.reception_area_text.setTextCursor(cursor)
        self.reception_area_text.ensureCursorVisible()

    def on_raw_data_received(self, raw_data):
        if self.reception_area_text._terminal_mode:
            if not self._text_cleared:
                self.reception_area_text.clear_terminal()
                self._text_cleared = True
            self.reception_area_text.feed_data(raw_data)

    def on_hex_data_received(self, hex_data):
        if not self._hex_cleared:
            self.reception_area_Hex_text.clear()
            self._hex_cleared = True
        
        display_hex = hex_data
        if self.timestamp_checkBox.isChecked() and not self.reception_area_text._terminal_mode:
            now = datetime.now()
            timestamp = now.strftime("%H:%M:%S.") + f"{now.microsecond // 1000:03d}"
            display_hex = f"[{timestamp}] {hex_data}"
        
        cursor = self.reception_area_Hex_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(display_hex)
        self.reception_area_Hex_text.setTextCursor(cursor)
        self.reception_area_Hex_text.ensureCursorVisible()

    def on_export_clicked(self, export_type="text"):
        if export_type == "text":
            text_content = self.reception_area_text.toPlainText()
            default_name = "serial_text_log.txt"
        else:
            text_content = self.reception_area_Hex_text.toPlainText()
            default_name = "serial_hex_log.txt"

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出文件",
            default_name,
            "文本文件 (*.txt);;所有文件 (*)"
        )

        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(text_content)
                self.show_success_info_bar("导出成功：", f"文件已保存到 {file_path}")
            except Exception as e:
                InfoBar.error(
                    title="导出失败：",
                    content=str(e),
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=3000,
                    parent=self,
                )

    def get_serial_ports(self):
        ports = []
        for port_info in serial.tools.list_ports.comports():
            description = f"{port_info.device} : {port_info.description}"
            ports.append(description)
        return ports

    def check_serial_ports(self):
        new_ports = self.get_serial_ports()
        current_port_data = self.port_combo.currentPortData()
        current_port_device = current_port_data.split(" : ")[0] if " : " in current_port_data else ""

        if set(new_ports) == set(self.current_ports):
            return

        added_ports = [p for p in new_ports if p not in self.current_ports]
        removed_ports = [p for p in self.current_ports if p not in new_ports]
        removed_devices = [p.split(" : ")[0] for p in removed_ports]

        if self.serial_port is not None and self.serial_port.is_open:
            if self.serial_port.port in removed_devices:
                self._handle_serial_unplugged()

        self.port_combo.blockSignals(True)
        self.port_combo.addPortItems(new_ports)
        self.current_ports = new_ports

        if current_port_device:
            self.port_combo.setCurrentPortByDevice(current_port_device)
        elif new_ports:
            self.port_combo.setCurrentIndex(0)
            self.last_port_combo_text = ""
        self.port_combo.blockSignals(False)

        if added_ports and not self._is_first_load:
            self._show_ports_added_info(added_ports)

        if removed_ports and not self._is_first_load:
            self._show_ports_removed_info(removed_ports)

        if self._is_first_load and new_ports:
            self._is_first_load = False

    def _handle_serial_unplugged(self):
        if hasattr(self, "data_read_thread") and self.data_read_thread is not None:
            self.data_read_thread.running = False
            try:
                self.data_read_thread.hex_data_received.disconnect(self.on_hex_data_received)
            except TypeError:
                pass
            self.data_read_thread = None

        if self.serial_port is not None:
            try:
                self.serial_port.close()
            except:
                pass
            self.serial_port = None

        self.serial_start_pushbutton.setChecked(False)
        self.serial_start_pushbutton.setText("开始监视")
        self.serial_start_pushbutton.setIcon(FIF.PLAY_SOLID)

        InfoBar.warning(
            title="串口已断开",
            content="当前连接的串口已被拔出",
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=3000,
            parent=self,
        )

    def _show_ports_added_info(self, added_ports):
        numbered_ports = [f"{i + 1}. {port}" for i, port in enumerate(added_ports)]
        InfoBar.success(
            title="检测到新串口",
            content=f"新增：<br>{'<br>'.join(numbered_ports)}",
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=2000,
            parent=self,
        )

    def _show_ports_removed_info(self, removed_ports):
        InfoBar.warning(
            title="检测到串口移除",
            content=f"已移除：{', '.join(removed_ports)}",
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=2000,
            parent=self,
        )

    def on_combobox_changed(self, combo_box, title_prefix):
        current_text = combo_box.currentText()
        last_text_attr = f"last_{combo_box.objectName()}_text"
        
        if current_text and current_text != getattr(self, last_text_attr, None):
            self.show_success_info_bar(
                title=f"{title_prefix}成功设置为：", content=current_text
            )
            setattr(self, last_text_attr, current_text)
            self.serial_text_buffer.clear()

    def show_success_info_bar(self, title, content, duration=2000):
        InfoBar.success(
            title=title,
            content=content,
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=duration,
            parent=self,
        )

    def handle_error_occurred(self, error_message):
        InfoBar.error(
            title="串口连接失败:",
            content=error_message,
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.BOTTOM_RIGHT,
            duration=15000,
            parent=self,
        )

    def add_sub_interface(self, widget: QWidget, object_name, text):
        widget.setObjectName(object_name)
        self.stackedWidget.addWidget(widget)
        self.pivot.addItem(routeKey=object_name, text=text)

    def on_send_format_changed(self, index):
        self._send_hex_mode = (index == 1)
        mode = "Hex" if self._send_hex_mode else "文本"
        self.show_success_info_bar("发送格式：", f"已切换为{mode}发送", 1000)

    def clear_send_area(self):
        self.send_area_text.clear()
        self.show_success_info_bar("发送栏：", "已清空发送区", 1000)

    def change_send_area_fontsize(self, value):
        font = QFont("Microsoft YaHei", value)
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias | QFont.StyleStrategy.PreferQuality)
        self.send_area_text.setFont(font)
        cfg.set(cfg.serialSendFontSize, value)

    def on_send_clicked(self):
        if self.serial_port is None or not self.serial_port.is_open:
            InfoBar.warning(
                title="发送失败：",
                content="请先连接串口",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=2000,
                parent=self,
            )
            return

        text = self.send_area_text.toPlainText().strip()
        if not text:
            return

        try:
            if self._send_hex_mode:
                hex_text = text.replace(" ", "").replace("\n", "").replace("\r", "")
                if len(hex_text) % 2 != 0:
                    raise ValueError("Hex数据长度必须为偶数")
                data = bytes.fromhex(hex_text)
            else:
                data = text.encode('utf-8')
            
            self.serial_port.write(data)
            self.send_area_text.add_to_history(text)
            self.show_success_info_bar("发送成功：", f"已发送 {len(data)} 字节", 1000)
            
            if self.auto_clear_checkbox.isChecked():
                self.send_area_text.clear()
        except Exception as e:
            InfoBar.error(
                title="发送失败：",
                content=str(e),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )

    def on_ymodem_send_clicked(self):
        if self.serial_port is None or not self.serial_port.is_open:
            InfoBar.warning(
                title="发送失败：",
                content="请先连接串口",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=2000,
                parent=self,
            )
            return

        file_dialog = QFileDialog(self)
        file_dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
        file_dialog.setWindowTitle("选择要发送的文件")
        
        if file_dialog.exec():
            selected_files = file_dialog.selectedFiles()
            if selected_files:
                # 显示一次InfoBar提示，显示当前要发送的文件，并保存引用以便完成后关闭
                file_names = [os.path.basename(file) for file in selected_files]
                self.ymodem_info_bar = InfoBar.info(
                    title="YMODEM发送",
                    content=f"正在发送：{', '.join(file_names)}",
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=300000,
                    parent=self,
                )
                self._ymodem_send_files(selected_files)

    def _ymodem_send_files(self, file_paths):
        # 显示进度环
        self.ymodem_progress_ring.show()
        self.ymodem_progress_ring.setValue(0)
        
        # 创建并启动YMODEM发送线程
        self.ymodem_send_thread = YModem_Send_Thread(self.serial_port, file_paths)
        self.ymodem_send_thread.progress_updated.connect(self._on_ymodem_progress_updated)
        self.ymodem_send_thread.send_completed.connect(self._on_ymodem_send_completed)
        self.ymodem_send_thread.start()

    def _on_ymodem_progress_updated(self, task_index, task_name, total_packets, success_packets):
        progress = (success_packets / total_packets) * 100 if total_packets > 0 else 0
        self.ymodem_progress_ring.setValue(int(progress))

    def _on_ymodem_send_completed(self, success, message):
        # 关闭发送中的InfoBar提示
        if hasattr(self, 'ymodem_info_bar') and self.ymodem_info_bar:
            self.ymodem_info_bar.close()
        
        # 隐藏进度环
        self.ymodem_progress_ring.hide()
        self.ymodem_progress_ring.setValue(0)
        
        # 在右上角显示结果信息
        if success:
            InfoBar.success(
                title="YMODEM发送成功",
                content=message,
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=3000,
                parent=self,
            )
        else:
            InfoBar.error(
                title="YMODEM发送失败",
                content=message,
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=3000,
                parent=self,
            )


if __name__ == "__main__":
    if cfg.get(cfg.dpiScale) == "Auto":
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    else:
        os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
        os.environ["QT_SCALE_FACTOR"] = str(cfg.get(cfg.dpiScale))

    app = QApplication(sys.argv)
    w = Serial_Tools_Widget()
    w.show()
    sys.exit(app.exec())
