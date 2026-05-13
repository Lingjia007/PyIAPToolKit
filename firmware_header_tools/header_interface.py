# coding:utf-8
import sys
import os
import struct
import zlib
from datetime import datetime
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFileDialog,
    QGroupBox,
    QGridLayout,
    QSpacerItem,
    QSizePolicy,
)

from qfluentwidgets import (
    FluentIcon as FIF,
    InfoBar,
    InfoBarPosition,
    BodyLabel,
    StrongBodyLabel,
    PushButton,
    LineEdit,
    SpinBox,
    PlainTextEdit,
    isDarkTheme,
    ComboBox,
    CheckBox,
    CardWidget,
)

from settings.config import cfg


FIRMWARE_MAGIC = b'FWHD'
HEADER_VERSION = 1
HEADER_SIZE = 64


class FirmwareHeader:
    MAGIC = FIRMWARE_MAGIC
    HEADER_SIZE = HEADER_SIZE
    
    def __init__(self):
        self.magic = FIRMWARE_MAGIC
        self.header_version = HEADER_VERSION
        self.firmware_version_major = 1
        self.firmware_version_minor = 0
        self.firmware_version_patch = 0
        self.firmware_version_build = 0
        self.firmware_size = 0
        self.firmware_crc32 = 0
        self.timestamp = 0
        self.encryption_flag = 0
        self.reserved = bytes(24)
    
    def to_bytes(self):
        return struct.pack(
            '<4sHHBBBBIIIB24s',
            self.magic,
            self.header_version,
            self.firmware_version_major,
            self.firmware_version_minor,
            self.firmware_version_patch,
            self.firmware_version_build,
            0,
            self.firmware_size,
            self.firmware_crc32,
            self.timestamp,
            self.encryption_flag,
            self.reserved
        )
    
    @classmethod
    def from_bytes(cls, data):
        if len(data) < cls.HEADER_SIZE:
            raise ValueError(f"数据长度不足，需要至少 {cls.HEADER_SIZE} 字节")
        
        header = cls()
        unpacked = struct.unpack('<4sHHBBBBIIIB24s', data[:cls.HEADER_SIZE])
        
        header.magic = unpacked[0]
        header.header_version = unpacked[1]
        header.firmware_version_major = unpacked[2]
        header.firmware_version_minor = unpacked[3]
        header.firmware_version_patch = unpacked[4]
        header.firmware_version_build = unpacked[5]
        header.firmware_size = unpacked[7]
        header.firmware_crc32 = unpacked[8]
        header.timestamp = unpacked[9]
        header.encryption_flag = unpacked[10]
        header.reserved = unpacked[11]
        
        return header
    
    def validate_magic(self):
        return self.magic == self.MAGIC
    
    def get_version_string(self):
        return f"v{self.firmware_version_major}.{self.firmware_version_minor}.{self.firmware_version_patch}.{self.firmware_version_build}"
    
    def get_timestamp_string(self):
        if self.timestamp == 0:
            return "未设置"
        try:
            dt = datetime.fromtimestamp(self.timestamp)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
            return "无效时间戳"
    
    def get_encryption_string(self):
        if self.encryption_flag == 0:
            return "未加密"
        elif self.encryption_flag == 1:
            return "AES-256-CBC"
        elif self.encryption_flag == 2:
            return "AES-256-ECB"
        elif self.encryption_flag == 3:
            return "AES-256-CTR"
        else:
            return f"未知 ({self.encryption_flag})"


class CalculateCrcThread(QThread):
    progress_updated = pyqtSignal(int)
    crc_calculated = pyqtSignal(int)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, file_path, skip_header=True):
        super().__init__()
        self.file_path = file_path
        self.skip_header = skip_header
    
    def run(self):
        try:
            file_size = os.path.getsize(self.file_path)
            chunk_size = 65536
            crc = 0
            
            with open(self.file_path, 'rb') as f:
                if self.skip_header:
                    f.seek(HEADER_SIZE)
                    file_size -= HEADER_SIZE
                
                total_read = 0
                while True:
                    data = f.read(chunk_size)
                    if not data:
                        break
                    crc = zlib.crc32(data, crc)
                    total_read += len(data)
                    progress = int(total_read / max(file_size, 1) * 100)
                    self.progress_updated.emit(progress)
            
            self.crc_calculated.emit(crc & 0xFFFFFFFF)
        except Exception as e:
            self.error_occurred.emit(str(e))


class FirmwareHeader_Widget(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("firmware_header_widget")
        self.resize(1000, 700)
        
        self.Main_hLayout = QHBoxLayout(self)
        self.header_setting_vBoxLayout = QVBoxLayout()
        self.header_setting_vBoxLayout.setSpacing(10)
        self.header_setting_vBoxLayout.setContentsMargins(30, 30, 30, 30)
        
        self.header = FirmwareHeader()
        self.crc_thread = None
        
        self._init_file_ui()
        self._init_header_editor_ui()
        self._init_operations_ui()
        
        self.Main_hLayout.addLayout(self.header_setting_vBoxLayout, 1)
        self._init_output_bar_ui()
        
        self.__updateTheme()
        cfg.themeChanged.connect(self.__updateTheme)
    
    def _init_file_ui(self):
        self.file_group = QGroupBox("固件文件")
        file_layout = QVBoxLayout()
        file_layout.setSpacing(12)
        
        input_label = BodyLabel("固件文件:")
        self.input_file_lineedit = LineEdit()
        self.input_file_lineedit.setPlaceholderText("选择 .bin 或 .bin.aes 固件文件")
        self.browse_input_button = PushButton(FIF.FOLDER, "浏览", self)
        self.browse_input_button.clicked.connect(self._browse_input_file)
        input_hlayout = QHBoxLayout()
        input_hlayout.addWidget(input_label)
        input_hlayout.addWidget(self.input_file_lineedit, 1)
        input_hlayout.addWidget(self.browse_input_button)
        file_layout.addLayout(input_hlayout)
        
        output_label = BodyLabel("输出文件:")
        self.output_file_lineedit = LineEdit()
        self.output_file_lineedit.setPlaceholderText("输出固件路径（可选，默认覆盖原文件）")
        self.browse_output_button = PushButton(FIF.FOLDER, "浏览", self)
        self.browse_output_button.clicked.connect(self._browse_output_file)
        output_hlayout = QHBoxLayout()
        output_hlayout.addWidget(output_label)
        output_hlayout.addWidget(self.output_file_lineedit, 1)
        output_hlayout.addWidget(self.browse_output_button)
        file_layout.addLayout(output_hlayout)
        
        self.file_group.setLayout(file_layout)
        self.header_setting_vBoxLayout.addWidget(self.file_group)
    
    def _init_header_editor_ui(self):
        self.editor_group = QGroupBox("头部编辑器")
        editor_layout = QGridLayout()
        editor_layout.setSpacing(10)
        
        row = 0
        
        magic_label = BodyLabel("魔术字 (Magic):")
        self.magic_lineedit = LineEdit()
        self.magic_lineedit.setText("FWHD")
        self.magic_lineedit.setMaxLength(4)
        self.magic_lineedit.setToolTip("4字节魔术字，用于识别固件类型")
        editor_layout.addWidget(magic_label, row, 0)
        editor_layout.addWidget(self.magic_lineedit, row, 1)
        
        header_ver_label = BodyLabel("头部版本:")
        self.header_ver_spinbox = SpinBox()
        self.header_ver_spinbox.setRange(1, 65535)
        self.header_ver_spinbox.setValue(1)
        editor_layout.addWidget(header_ver_label, row, 2)
        editor_layout.addWidget(self.header_ver_spinbox, row, 3)
        row += 1
        
        version_title = StrongBodyLabel("固件版本:")
        editor_layout.addWidget(version_title, row, 0, 1, 4)
        row += 1
        
        major_label = BodyLabel("主版本 (Major):")
        self.major_spinbox = SpinBox()
        self.major_spinbox.setRange(0, 255)
        self.major_spinbox.setValue(1)
        editor_layout.addWidget(major_label, row, 0)
        editor_layout.addWidget(self.major_spinbox, row, 1)
        
        minor_label = BodyLabel("次版本 (Minor):")
        self.minor_spinbox = SpinBox()
        self.minor_spinbox.setRange(0, 255)
        self.minor_spinbox.setValue(0)
        editor_layout.addWidget(minor_label, row, 2)
        editor_layout.addWidget(self.minor_spinbox, row, 3)
        row += 1
        
        patch_label = BodyLabel("补丁版本 (Patch):")
        self.patch_spinbox = SpinBox()
        self.patch_spinbox.setRange(0, 255)
        self.patch_spinbox.setValue(0)
        editor_layout.addWidget(patch_label, row, 0)
        editor_layout.addWidget(self.patch_spinbox, row, 1)
        
        build_label = BodyLabel("构建号 (Build):")
        self.build_spinbox = SpinBox()
        self.build_spinbox.setRange(0, 255)
        self.build_spinbox.setValue(0)
        editor_layout.addWidget(build_label, row, 2)
        editor_layout.addWidget(self.build_spinbox, row, 3)
        row += 1
        
        size_label = BodyLabel("固件大小:")
        self.size_lineedit = LineEdit()
        self.size_lineedit.setReadOnly(True)
        self.size_lineedit.setText("0 字节")
        editor_layout.addWidget(size_label, row, 0)
        editor_layout.addWidget(self.size_lineedit, row, 1)
        
        crc_label = BodyLabel("CRC32校验:")
        self.crc_lineedit = LineEdit()
        self.crc_lineedit.setReadOnly(True)
        self.crc_lineedit.setPlaceholderText("点击计算CRC32")
        self.calculate_crc_button = PushButton(FIF.CALORIES, "计算", self)
        self.calculate_crc_button.clicked.connect(self._calculate_crc)
        crc_hlayout = QHBoxLayout()
        crc_hlayout.addWidget(self.crc_lineedit)
        crc_hlayout.addWidget(self.calculate_crc_button)
        editor_layout.addWidget(crc_label, row, 2)
        editor_layout.addLayout(crc_hlayout, row, 3)
        row += 1
        
        timestamp_label = BodyLabel("时间戳:")
        self.timestamp_lineedit = LineEdit()
        self.timestamp_lineedit.setReadOnly(True)
        self.timestamp_lineedit.setPlaceholderText("点击设置当前时间")
        self.set_timestamp_button = PushButton(FIF.DATE_TIME, "设置", self)
        self.set_timestamp_button.clicked.connect(self._set_current_timestamp)
        timestamp_hlayout = QHBoxLayout()
        timestamp_hlayout.addWidget(self.timestamp_lineedit)
        timestamp_hlayout.addWidget(self.set_timestamp_button)
        editor_layout.addWidget(timestamp_label, row, 0)
        editor_layout.addLayout(timestamp_hlayout, row, 1)
        
        encryption_label = BodyLabel("加密标志:")
        self.encryption_combo = ComboBox()
        self.encryption_combo.addItems([
            "未加密 (0)",
            "AES-256-CBC (1)",
            "AES-256-ECB (2)",
            "AES-256-CTR (3)"
        ])
        self.encryption_combo.setCurrentIndex(0)
        self.encryption_combo.setFixedWidth(150)
        editor_layout.addWidget(encryption_label, row, 2)
        editor_layout.addWidget(self.encryption_combo, row, 3)
        row += 1
        
        reserved_label = BodyLabel("保留字段 (Hex):")
        self.reserved_lineedit = LineEdit()
        self.reserved_lineedit.setPlaceholderText("24字节保留字段（十六进制）")
        self.reserved_lineedit.setMaxLength(48)
        editor_layout.addWidget(reserved_label, row, 0, 1, 2)
        editor_layout.addWidget(self.reserved_lineedit, row, 2, 1, 2)
        
        self.editor_group.setLayout(editor_layout)
        self.header_setting_vBoxLayout.addWidget(self.editor_group)
    
    def _init_operations_ui(self):
        self.operations_group = QGroupBox("操作")
        operations_layout = QVBoxLayout()
        operations_layout.setSpacing(12)
        
        self.auto_fill_button = PushButton(FIF.SYNC, "自动填充", self)
        self.auto_fill_button.setToolTip("自动填充固件大小和CRC32校验")
        self.auto_fill_button.clicked.connect(self._auto_fill_header)
        operations_layout.addWidget(self.auto_fill_button)
        
        btn_hlayout = QHBoxLayout()
        
        self.parse_button = PushButton(FIF.SEARCH, "解析头部", self)
        self.parse_button.setToolTip("从固件文件解析头部信息")
        self.parse_button.clicked.connect(self._parse_header)
        btn_hlayout.addWidget(self.parse_button)
        
        self.write_button = PushButton(FIF.SAVE, "写入头部", self)
        self.write_button.setToolTip("将头部信息写入固件文件")
        self.write_button.clicked.connect(self._write_header)
        btn_hlayout.addWidget(self.write_button)
        
        operations_layout.addLayout(btn_hlayout)
        
        self.backup_checkbox = CheckBox("写入前备份原文件", self)
        self.backup_checkbox.setChecked(True)
        operations_layout.addWidget(self.backup_checkbox)
        
        self.operations_group.setLayout(operations_layout)
        self.header_setting_vBoxLayout.addWidget(self.operations_group)
        self.header_setting_vBoxLayout.addStretch(1)
    
    def _init_output_bar_ui(self):
        self.right_vBoxLayout = QVBoxLayout()
        self.right_vBoxLayout.setSpacing(0)
        self.right_vBoxLayout.setContentsMargins(0, 0, 0, 0)
        
        self.output_bar_widget = QWidget()
        self.output_bar_vBoxLayout = QVBoxLayout(self.output_bar_widget)
        self.output_bar_vBoxLayout.setContentsMargins(5, 0, 0, 0)
        
        header_layout = QHBoxLayout()
        header_label = BodyLabel("输出日志")
        header_layout.addWidget(header_label)
        header_layout.addStretch(1)
        
        self.clear_output_button = PushButton(FIF.DELETE, "清空", self)
        self.clear_output_button.clicked.connect(self._clear_output)
        header_layout.addWidget(self.clear_output_button)
        
        self.export_output_button = PushButton(FIF.SAVE, "导出", self)
        self.export_output_button.clicked.connect(self._export_output)
        header_layout.addWidget(self.export_output_button)
        
        self.output_bar_vBoxLayout.addLayout(header_layout)
        
        self.output_area_text = PlainTextEdit()
        self.output_area_text.setReadOnly(True)
        self.output_bar_vBoxLayout.addWidget(self.output_area_text)
        
        self.right_vBoxLayout.addWidget(self.output_bar_widget, 1)
        self.Main_hLayout.addLayout(self.right_vBoxLayout, 1)
    
    def __updateTheme(self):
        is_dark = isDarkTheme()
        text_color = "#ffffff" if is_dark else "#000000"
        
        widgets_to_update = [
            getattr(self, 'file_group', None),
            getattr(self, 'editor_group', None),
            getattr(self, 'operations_group', None),
        ]
        
        for widget in widgets_to_update:
            if widget:
                widget.setStyleSheet(f"color: {text_color};")
    
    def _log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.output_area_text.appendPlainText(f"[{timestamp}] {message}")
    
    def _clear_output(self):
        self.output_area_text.clear()
    
    def _export_output(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出输出", "header_output.txt", "文本文件 (*.txt);;所有文件 (*)"
        )
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(self.output_area_text.toPlainText())
                InfoBar.success(
                    title="导出成功",
                    content=f"输出已保存到 {file_path}",
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=3000,
                    parent=self,
                )
            except Exception as e:
                InfoBar.error(
                    title="导出失败",
                    content=str(e),
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=3000,
                    parent=self,
                )
    
    def _browse_input_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择固件文件",
            "",
            "固件文件 (*.bin *.bin.aes *.aes);;所有文件 (*.*)"
        )
        if file_path:
            self.input_file_lineedit.setText(file_path)
            self._log(f"已选择固件文件: {file_path}")
            
            file_size = os.path.getsize(file_path)
            self.size_lineedit.setText(f"{file_size:,} 字节")
            self.header.firmware_size = file_size
            
            if not self.output_file_lineedit.text():
                self.output_file_lineedit.setText(file_path)
    
    def _browse_output_file(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "选择输出文件",
            "",
            "固件文件 (*.bin);;所有文件 (*.*)"
        )
        if file_path:
            self.output_file_lineedit.setText(file_path)
            self._log(f"输出文件: {file_path}")
    
    def _set_current_timestamp(self):
        timestamp = int(datetime.now().timestamp())
        self.header.timestamp = timestamp
        self.timestamp_lineedit.setText(self.header.get_timestamp_string())
        self._log(f"已设置时间戳: {self.header.get_timestamp_string()}")
    
    def _calculate_crc(self):
        input_file = self.input_file_lineedit.text().strip()
        if not input_file:
            InfoBar.warning(
                title="警告",
                content="请先选择固件文件",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return
        
        if not os.path.exists(input_file):
            InfoBar.error(
                title="错误",
                content="固件文件不存在",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return
        
        self.calculate_crc_button.setEnabled(False)
        self.calculate_crc_button.setText("计算中...")
        self._log("开始计算CRC32...")
        
        self.crc_thread = CalculateCrcThread(input_file, skip_header=True)
        self.crc_thread.progress_updated.connect(self._on_crc_progress)
        self.crc_thread.crc_calculated.connect(self._on_crc_calculated)
        self.crc_thread.error_occurred.connect(self._on_crc_error)
        self.crc_thread.start()
    
    def _on_crc_progress(self, progress):
        pass
    
    def _on_crc_calculated(self, crc):
        self.header.firmware_crc32 = crc
        self.crc_lineedit.setText(f"0x{crc:08X}")
        self.calculate_crc_button.setEnabled(True)
        self.calculate_crc_button.setText("计算")
        self._log(f"CRC32计算完成: 0x{crc:08X}")
        
        InfoBar.success(
            title="计算完成",
            content=f"CRC32: 0x{crc:08X}",
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=3000,
            parent=self,
        )
    
    def _on_crc_error(self, error):
        self.calculate_crc_button.setEnabled(True)
        self.calculate_crc_button.setText("计算")
        self._log(f"CRC32计算失败: {error}")
        InfoBar.error(
            title="计算失败",
            content=error,
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=3000,
            parent=self,
        )
    
    def _auto_fill_header(self):
        input_file = self.input_file_lineedit.text().strip()
        if not input_file:
            InfoBar.warning(
                title="警告",
                content="请先选择固件文件",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return
        
        if not os.path.exists(input_file):
            InfoBar.error(
                title="错误",
                content="固件文件不存在",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return
        
        file_size = os.path.getsize(input_file)
        self.header.firmware_size = file_size
        self.size_lineedit.setText(f"{file_size:,} 字节")
        
        self._set_current_timestamp()
        
        self._calculate_crc()
        
        self._log("自动填充完成")
    
    def _get_header_from_ui(self):
        header = FirmwareHeader()
        
        magic_text = self.magic_lineedit.text()
        if len(magic_text) != 4:
            header.magic = magic_text.encode('utf-8').ljust(4, b'\x00')[:4]
        else:
            header.magic = magic_text.encode('utf-8')
        
        header.header_version = self.header_ver_spinbox.value()
        header.firmware_version_major = self.major_spinbox.value()
        header.firmware_version_minor = self.minor_spinbox.value()
        header.firmware_version_patch = self.patch_spinbox.value()
        header.firmware_version_build = self.build_spinbox.value()
        header.firmware_size = self.header.firmware_size
        header.firmware_crc32 = self.header.firmware_crc32
        header.timestamp = self.header.timestamp
        header.encryption_flag = self.encryption_combo.currentIndex()
        
        reserved_hex = self.reserved_lineedit.text().strip()
        if reserved_hex:
            try:
                header.reserved = bytes.fromhex(reserved_hex).ljust(24, b'\x00')[:24]
            except ValueError:
                header.reserved = bytes(24)
        else:
            header.reserved = bytes(24)
        
        return header
    
    def _set_ui_from_header(self, header):
        self.magic_lineedit.setText(header.magic.decode('utf-8', errors='replace'))
        self.header_ver_spinbox.setValue(header.header_version)
        self.major_spinbox.setValue(header.firmware_version_major)
        self.minor_spinbox.setValue(header.firmware_version_minor)
        self.patch_spinbox.setValue(header.firmware_version_patch)
        self.build_spinbox.setValue(header.firmware_version_build)
        self.size_lineedit.setText(f"{header.firmware_size:,} 字节")
        self.crc_lineedit.setText(f"0x{header.firmware_crc32:08X}")
        self.timestamp_lineedit.setText(header.get_timestamp_string())
        self.encryption_combo.setCurrentIndex(header.encryption_flag)
        
        if header.reserved != bytes(24):
            self.reserved_lineedit.setText(header.reserved.hex())
        
        self.header = header
    
    def _parse_header(self):
        input_file = self.input_file_lineedit.text().strip()
        if not input_file:
            InfoBar.warning(
                title="警告",
                content="请先选择固件文件",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return
        
        if not os.path.exists(input_file):
            InfoBar.error(
                title="错误",
                content="固件文件不存在",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return
        
        try:
            with open(input_file, 'rb') as f:
                header_data = f.read(HEADER_SIZE)
            
            if len(header_data) < HEADER_SIZE:
                InfoBar.error(
                    title="错误",
                    content=f"文件太小，无法解析头部（需要至少 {HEADER_SIZE} 字节）",
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=3000,
                    parent=self,
                )
                return
            
            header = FirmwareHeader.from_bytes(header_data)
            
            self._set_ui_from_header(header)
            
            self._log("=" * 50)
            self._log("头部解析成功:")
            self._log(f"  魔术字: {header.magic}")
            self._log(f"  头部版本: {header.header_version}")
            self._log(f"  固件版本: {header.get_version_string()}")
            self._log(f"  固件大小: {header.firmware_size:,} 字节")
            self._log(f"  CRC32: 0x{header.firmware_crc32:08X}")
            self._log(f"  时间戳: {header.get_timestamp_string()}")
            self._log(f"  加密标志: {header.get_encryption_string()}")
            self._log(f"  魔术字验证: {'通过' if header.validate_magic() else '失败'}")
            self._log("=" * 50)
            
            InfoBar.success(
                title="解析成功",
                content=f"头部版本: {header.get_version_string()}",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            
        except Exception as e:
            self._log(f"解析失败: {str(e)}")
            InfoBar.error(
                title="解析失败",
                content=str(e),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
    
    def _write_header(self):
        input_file = self.input_file_lineedit.text().strip()
        if not input_file:
            InfoBar.warning(
                title="警告",
                content="请先选择固件文件",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return
        
        if not os.path.exists(input_file):
            InfoBar.error(
                title="错误",
                content="固件文件不存在",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return
        
        output_file = self.output_file_lineedit.text().strip()
        if not output_file:
            output_file = input_file
        
        try:
            header = self._get_header_from_ui()
            
            if self.backup_checkbox.isChecked() and output_file == input_file:
                backup_file = input_file + ".bak"
                import shutil
                shutil.copy2(input_file, backup_file)
                self._log(f"已备份原文件到: {backup_file}")
            
            with open(input_file, 'rb') as f:
                firmware_data = f.read()
            
            if len(firmware_data) < HEADER_SIZE:
                firmware_data = firmware_data.ljust(HEADER_SIZE, b'\xFF')
            
            header_bytes = header.to_bytes()
            new_firmware_data = header_bytes + firmware_data[HEADER_SIZE:]
            
            with open(output_file, 'wb') as f:
                f.write(new_firmware_data)
            
            self._log("=" * 50)
            self._log("头部写入成功:")
            self._log(f"  输出文件: {output_file}")
            self._log(f"  头部大小: {HEADER_SIZE} 字节")
            self._log(f"  固件版本: {header.get_version_string()}")
            self._log(f"  固件大小: {header.firmware_size:,} 字节")
            self._log(f"  CRC32: 0x{header.firmware_crc32:08X}")
            self._log(f"  时间戳: {header.get_timestamp_string()}")
            self._log(f"  加密标志: {header.get_encryption_string()}")
            self._log("=" * 50)
            
            InfoBar.success(
                title="写入成功",
                content=f"头部已写入到 {output_file}",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            
        except Exception as e:
            self._log(f"写入失败: {str(e)}")
            InfoBar.error(
                title="写入失败",
                content=str(e),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )


if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    w = FirmwareHeader_Widget()
    w.show()
    sys.exit(app.exec())
