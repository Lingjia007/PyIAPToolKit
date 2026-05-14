# coding:utf-8
import sys
import os
import struct
import base64
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
    ScrollArea,
)

from settings.config import cfg

try:
    from Crypto.Hash import SHA256, HMAC
    from Crypto.PublicKey import ECC
    from Crypto.Signature import eddsa
    from Crypto.Hash import SHA512
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False


FIRMWARE_MAGIC = b'IAP\x01'
HEADER_VERSION = 1
HEADER_SIZE = 64
HEADER_PREFIX_SIZE = 32
DYNAMICSALT_SIZE = 16
IV_SIZE = 16
SIGNATURE_SIZE = 64


def hkdf_extract(salt: bytes, ikm: bytes) -> bytes:
    prk = HMAC.new(salt, ikm, digestmod=SHA256).digest()
    return prk


def hkdf_expand(prk: bytes, info: bytes, length: int) -> bytes:
    hash_len = SHA256.digest_size
    n = (length + hash_len - 1) // hash_len
    okm = b''
    t = b''
    for i in range(1, n + 1):
        t = HMAC.new(prk, t + info + bytes([i]), digestmod=SHA256).digest()
        okm += t
    return okm[:length]


class FirmwareHeader:
    MAGIC = FIRMWARE_MAGIC
    HEADER_SIZE = HEADER_SIZE
    PREFIX_FORMAT = '<4sBBBBIBBBIII5s'
    FULL_FORMAT = '<4sBBBBIBBBIII5s32s'

    IMAGE_TYPE_APP = 0x01
    ENCRYPTION_AES_256_CBC = 0x01
    SIGNATURE_ED25519 = 0x01

    def __init__(self):
        self.magic = FIRMWARE_MAGIC
        self.header_version = HEADER_VERSION
        self.firmware_version_major = 1
        self.firmware_version_minor = 0
        self.firmware_version_patch = 0
        self.total_payload_size = 0
        self.image_type = self.IMAGE_TYPE_APP
        self.encryption_algorithm = self.ENCRYPTION_AES_256_CBC
        self.signature_algorithm = self.SIGNATURE_ED25519
        self.hardware_compatibility = 0
        self.security_counter = 0
        self.build_timestamp = 0
        self.reserved = bytes(5)
        self.header_checksum = bytes(32)

    def _pack_prefix(self):
        return struct.pack(
            self.PREFIX_FORMAT,
            self.magic,
            self.header_version,
            self.firmware_version_major,
            self.firmware_version_minor,
            self.firmware_version_patch,
            self.total_payload_size,
            self.image_type,
            self.encryption_algorithm,
            self.signature_algorithm,
            self.hardware_compatibility,
            self.security_counter,
            self.build_timestamp,
            self.reserved
        )

    def compute_checksum(self, devkey):
        prefix = self._pack_prefix()
        self.header_checksum = HMAC.new(devkey, prefix, digestmod=SHA256).digest()

    def verify_checksum(self, devkey):
        prefix = self._pack_prefix()
        expected = HMAC.new(devkey, prefix, digestmod=SHA256).digest()
        return self.header_checksum == expected

    def to_bytes(self):
        return self._pack_prefix() + self.header_checksum

    @classmethod
    def from_bytes(cls, data):
        if len(data) < cls.HEADER_SIZE:
            raise ValueError(f"数据长度不足，需要至少 {cls.HEADER_SIZE} 字节")
        header = cls()
        unpacked = struct.unpack(cls.FULL_FORMAT, data[:cls.HEADER_SIZE])
        header.magic = unpacked[0]
        header.header_version = unpacked[1]
        header.firmware_version_major = unpacked[2]
        header.firmware_version_minor = unpacked[3]
        header.firmware_version_patch = unpacked[4]
        header.total_payload_size = unpacked[5]
        header.image_type = unpacked[6]
        header.encryption_algorithm = unpacked[7]
        header.signature_algorithm = unpacked[8]
        header.hardware_compatibility = unpacked[9]
        header.security_counter = unpacked[10]
        header.build_timestamp = unpacked[11]
        header.reserved = unpacked[12]
        header.header_checksum = unpacked[13]
        return header

    def validate_magic(self):
        return self.magic == self.MAGIC

    def get_version_string(self):
        return f"v{self.firmware_version_major}.{self.firmware_version_minor}.{self.firmware_version_patch}"

    def get_timestamp_string(self):
        if self.build_timestamp == 0:
            return "未设置"
        try:
            dt = datetime.fromtimestamp(self.build_timestamp)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
            return "无效时间戳"

    def get_image_type_string(self):
        types = {0x01: "App", 0x02: "Bootloader", 0x03: "Resource"}
        return types.get(self.image_type, f"未知 ({self.image_type})")

    def get_encryption_string(self):
        algos = {0x00: "无", 0x01: "AES-256-CBC", 0x02: "AES-256-ECB", 0x03: "AES-256-CTR"}
        return algos.get(self.encryption_algorithm, f"未知 ({self.encryption_algorithm})")

    def get_signature_string(self):
        algos = {0x00: "无", 0x01: "Ed25519"}
        return algos.get(self.signature_algorithm, f"未知 ({self.signature_algorithm})")


class PackageThread(QThread):
    progress_updated = pyqtSignal(int)
    package_completed = pyqtSignal(bool, str)
    error_occurred = pyqtSignal(str)

    def __init__(self, header, dynamic_salt, iv, encrypted_data,
                 ed25519_private_key_pem, output_path):
        super().__init__()
        self.header = header
        self.dynamic_salt = dynamic_salt
        self.iv = iv
        self.encrypted_data = encrypted_data
        self.ed25519_private_key_pem = ed25519_private_key_pem
        self.output_path = output_path

    def run(self):
        try:
            self.progress_updated.emit(10)

            payload = self.dynamic_salt + self.iv + self.encrypted_data
            header_bytes = self.header.to_bytes()

            self.progress_updated.emit(40)

            data_to_sign = header_bytes + payload
            private_key = ECC.import_key(self.ed25519_private_key_pem)
            signer = eddsa.new(private_key, 'rfc8032')
            hash_obj = SHA512.new(data_to_sign)
            signature = signer.sign(hash_obj.digest())

            self.progress_updated.emit(80)

            with open(self.output_path, 'wb') as f:
                f.write(header_bytes)
                f.write(payload)
                f.write(signature)

            self.progress_updated.emit(100)
            self.package_completed.emit(
                True,
                f"打包完成，输出文件: {self.output_path}\n"
                f"头部: {HEADER_SIZE} 字节\n"
                f"DynamicSalt: {DYNAMICSALT_SIZE} 字节\n"
                f"IV: {IV_SIZE} 字节\n"
                f"密文: {len(self.encrypted_data)} 字节\n"
                f"签名: {SIGNATURE_SIZE} 字节\n"
                f"总计: {HEADER_SIZE + len(payload) + SIGNATURE_SIZE} 字节"
            )
        except Exception as e:
            self.error_occurred.emit(f"打包失败: {str(e)}")


class FirmwareHeader_Widget(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("firmware_header_widget")
        self.resize(1000, 700)

        self.Main_hLayout = QHBoxLayout(self)
        self.Main_hLayout.setSpacing(0)
        self.Main_hLayout.setContentsMargins(0, 0, 0, 0)

        self.scroll_area = ScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.scroll_content = QWidget()
        self.scroll_content.setObjectName("scroll_content")
        self.header_setting_vBoxLayout = QVBoxLayout(self.scroll_content)
        self.header_setting_vBoxLayout.setSpacing(10)
        self.header_setting_vBoxLayout.setContentsMargins(30, 30, 30, 30)

        self.header = FirmwareHeader()
        self.package_thread = None
        self.ed25519_private_key_pem = None
        self.public_key_bytes = None

        self._init_file_ui()
        self._init_header_editor_ui()
        self._init_hkdf_ui()
        self._init_ed25519_ui()
        self._init_operations_ui()

        self.header_setting_vBoxLayout.addStretch(1)

        self.scroll_area.setWidget(self.scroll_content)
        self.Main_hLayout.addWidget(self.scroll_area, 3)
        self._init_output_bar_ui()

        self.__updateTheme()
        cfg.themeChanged.connect(self.__updateTheme)

    def _init_file_ui(self):
        self.file_group = QGroupBox("固件文件")
        file_layout = QVBoxLayout()
        file_layout.setSpacing(12)

        input_label = BodyLabel("加密固件文件:")
        self.input_file_lineedit = LineEdit()
        self.input_file_lineedit.setPlaceholderText("选择 AES 加密后的固件文件 (.bin.aes)，用于打包")
        self.browse_input_button = PushButton(FIF.FOLDER, "浏览", self)
        self.browse_input_button.clicked.connect(self._browse_input_file)
        input_hlayout = QHBoxLayout()
        input_hlayout.addWidget(input_label)
        input_hlayout.addWidget(self.input_file_lineedit, 1)
        input_hlayout.addWidget(self.browse_input_button)
        file_layout.addLayout(input_hlayout)

        output_label = BodyLabel("打包输出文件:")
        self.output_file_lineedit = LineEdit()
        self.output_file_lineedit.setPlaceholderText("打包后的固件路径（解析/验证也使用此路径）")
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
        self.editor_group = QGroupBox("头部编辑器 (64 字节)")
        editor_layout = QGridLayout()
        editor_layout.setSpacing(10)

        row = 0

        magic_label = BodyLabel("魔术字 (Magic):")
        self.magic_lineedit = LineEdit()
        self.magic_lineedit.setText(f"{FIRMWARE_MAGIC[:3].decode('ascii')}\\x{FIRMWARE_MAGIC[3]:02X}")
        self.magic_lineedit.setReadOnly(True)
        self.magic_lineedit.setToolTip(f"4字节魔术字，固定值 (Hex: {FIRMWARE_MAGIC.hex().upper()})")
        editor_layout.addWidget(magic_label, row, 0)
        editor_layout.addWidget(self.magic_lineedit, row, 1)

        header_ver_label = BodyLabel("头部版本:")
        self.header_ver_spinbox = SpinBox()
        self.header_ver_spinbox.setRange(1, 255)
        self.header_ver_spinbox.setValue(1)
        editor_layout.addWidget(header_ver_label, row, 2)
        editor_layout.addWidget(self.header_ver_spinbox, row, 3)
        row += 1

        version_title = StrongBodyLabel("固件版本 (主.次.修订):")
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

        patch_label = BodyLabel("修订版本 (Patch):")
        self.patch_spinbox = SpinBox()
        self.patch_spinbox.setRange(0, 255)
        self.patch_spinbox.setValue(0)
        editor_layout.addWidget(patch_label, row, 0)
        editor_layout.addWidget(self.patch_spinbox, row, 1)

        payload_size_label = BodyLabel("载荷总大小 (Salt+IV+密文):")
        self.payload_size_lineedit = LineEdit()
        self.payload_size_lineedit.setReadOnly(True)
        self.payload_size_lineedit.setText("0 字节")
        editor_layout.addWidget(payload_size_label, row, 2)
        editor_layout.addWidget(self.payload_size_lineedit, row, 3)
        row += 1

        image_type_label = BodyLabel("镜像类型:")
        self.image_type_combo = ComboBox()
        self.image_type_combo.addItems([
            "App (0x01)", "Bootloader (0x02)", "Resource (0x03)"
        ])
        self.image_type_combo.setCurrentIndex(0)
        self.image_type_combo.setFixedWidth(150)
        editor_layout.addWidget(image_type_label, row, 0)
        editor_layout.addWidget(self.image_type_combo, row, 1)

        encryption_label = BodyLabel("加密算法:")
        self.encryption_combo = ComboBox()
        self.encryption_combo.addItems([
            "无 (0x00)", "AES-256-CBC (0x01)", "AES-256-ECB (0x02)", "AES-256-CTR (0x03)"
        ])
        self.encryption_combo.setCurrentIndex(1)
        self.encryption_combo.setFixedWidth(150)
        editor_layout.addWidget(encryption_label, row, 2)
        editor_layout.addWidget(self.encryption_combo, row, 3)
        row += 1

        signature_label = BodyLabel("签名算法:")
        self.signature_combo = ComboBox()
        self.signature_combo.addItems(["无 (0x00)", "Ed25519 (0x01)"])
        self.signature_combo.setCurrentIndex(1)
        self.signature_combo.setFixedWidth(150)
        editor_layout.addWidget(signature_label, row, 0)
        editor_layout.addWidget(self.signature_combo, row, 1)

        hw_compat_label = BodyLabel("硬件兼容标识 (Hex):")
        self.hw_compat_lineedit = LineEdit()
        self.hw_compat_lineedit.setPlaceholderText("8个十六进制字符 (4字节)")
        self.hw_compat_lineedit.setMaxLength(8)
        editor_layout.addWidget(hw_compat_label, row, 2)
        editor_layout.addWidget(self.hw_compat_lineedit, row, 3)
        row += 1

        security_counter_label = BodyLabel("安全计数器 (Hex):")
        self.security_counter_lineedit = LineEdit()
        self.security_counter_lineedit.setPlaceholderText("8个十六进制字符 (4字节)，防回滚")
        self.security_counter_lineedit.setMaxLength(8)
        editor_layout.addWidget(security_counter_label, row, 0)
        editor_layout.addWidget(self.security_counter_lineedit, row, 1)

        timestamp_label = BodyLabel("构建时间戳:")
        self.timestamp_lineedit = LineEdit()
        self.timestamp_lineedit.setReadOnly(True)
        self.timestamp_lineedit.setPlaceholderText("点击设置当前时间")
        self.set_timestamp_button = PushButton(FIF.DATE_TIME, "设置", self)
        self.set_timestamp_button.clicked.connect(self._set_current_timestamp)
        timestamp_hlayout = QHBoxLayout()
        timestamp_hlayout.addWidget(self.timestamp_lineedit)
        timestamp_hlayout.addWidget(self.set_timestamp_button)
        editor_layout.addWidget(timestamp_label, row, 2)
        editor_layout.addLayout(timestamp_hlayout, row, 3)

        self.editor_group.setLayout(editor_layout)
        self.header_setting_vBoxLayout.addWidget(self.editor_group)

    def _init_hkdf_ui(self):
        self.hkdf_group = QGroupBox("HKDF 密钥派生 & 头部校验")
        hkdf_layout = QVBoxLayout()
        hkdf_layout.setSpacing(10)

        devkey_label = BodyLabel("DevKey (128位, Hex):")
        self.devkey_lineedit = LineEdit()
        self.devkey_lineedit.setPlaceholderText("设备密钥（32个十六进制字符），用于HMAC头部校验和HKDF派生")
        self.generate_devkey_button = PushButton(FIF.SYNC, "生成", self)
        self.generate_devkey_button.clicked.connect(self._generate_devkey)
        devkey_hlayout = QHBoxLayout()
        devkey_hlayout.addWidget(devkey_label)
        devkey_hlayout.addWidget(self.devkey_lineedit, 1)
        devkey_hlayout.addWidget(self.generate_devkey_button)
        hkdf_layout.addLayout(devkey_hlayout)

        uid_label = BodyLabel("UID (96位, Hex):")
        self.uid_lineedit = LineEdit()
        self.uid_lineedit.setPlaceholderText("芯片唯一ID（24个十六进制字符）")
        uid_hlayout = QHBoxLayout()
        uid_hlayout.addWidget(uid_label)
        uid_hlayout.addWidget(self.uid_lineedit, 1)
        hkdf_layout.addLayout(uid_hlayout)

        dynamicsalt_label = BodyLabel("DynamicSalt (128位, Hex):")
        self.dynamicsalt_lineedit = LineEdit()
        self.dynamicsalt_lineedit.setPlaceholderText("动态盐值（32个十六进制字符），每版固件不同，将写入载荷前导")
        self.generate_dynamicsalt_button = PushButton(FIF.SYNC, "生成", self)
        self.generate_dynamicsalt_button.clicked.connect(self._generate_dynamicsalt)
        dynamicsalt_hlayout = QHBoxLayout()
        dynamicsalt_hlayout.addWidget(dynamicsalt_label)
        dynamicsalt_hlayout.addWidget(self.dynamicsalt_lineedit, 1)
        dynamicsalt_hlayout.addWidget(self.generate_dynamicsalt_button)
        hkdf_layout.addLayout(dynamicsalt_hlayout)

        self.hkdf_derive_button = PushButton(FIF.CERTIFICATE, "HKDF派生AES密钥 (仅参考验证)", self)
        self.hkdf_derive_button.clicked.connect(self._derive_hkdf_key)
        hkdf_layout.addWidget(self.hkdf_derive_button)

        self.hkdf_group.setLayout(hkdf_layout)
        self.header_setting_vBoxLayout.addWidget(self.hkdf_group)

    def _init_ed25519_ui(self):
        self.ed25519_group = QGroupBox("Ed25519 签名")
        ed25519_layout = QVBoxLayout()
        ed25519_layout.setSpacing(10)

        private_key_label = BodyLabel("私钥 (Hex, 32字节):")
        self.private_key_lineedit = LineEdit()
        self.private_key_lineedit.setPlaceholderText("64个十六进制字符")
        self.private_key_lineedit.setReadOnly(True)
        self.generate_key_button = PushButton(FIF.CERTIFICATE, "生成", self)
        self.generate_key_button.clicked.connect(self._generate_ed25519_key)
        self.load_key_button = PushButton(FIF.FOLDER, "加载", self)
        self.load_key_button.clicked.connect(self._load_ed25519_key)
        private_key_hlayout = QHBoxLayout()
        private_key_hlayout.addWidget(private_key_label)
        private_key_hlayout.addWidget(self.private_key_lineedit, 1)
        private_key_hlayout.addWidget(self.generate_key_button)
        private_key_hlayout.addWidget(self.load_key_button)
        ed25519_layout.addLayout(private_key_hlayout)

        public_key_label = BodyLabel("公钥 (Hex, 32字节):")
        self.public_key_lineedit = LineEdit()
        self.public_key_lineedit.setPlaceholderText("64个十六进制字符")
        self.public_key_lineedit.setReadOnly(True)
        public_key_hlayout = QHBoxLayout()
        public_key_hlayout.addWidget(public_key_label)
        public_key_hlayout.addWidget(self.public_key_lineedit, 1)
        ed25519_layout.addLayout(public_key_hlayout)

        self.ed25519_group.setLayout(ed25519_layout)
        self.header_setting_vBoxLayout.addWidget(self.ed25519_group)

    def _init_operations_ui(self):
        self.operations_group = QGroupBox("操作")
        operations_layout = QVBoxLayout()
        operations_layout.setSpacing(12)

        self.auto_fill_button = PushButton(FIF.SYNC, "自动填充", self)
        self.auto_fill_button.setToolTip("自动填充载荷大小、时间戳和动态盐值")
        self.auto_fill_button.clicked.connect(self._auto_fill)
        operations_layout.addWidget(self.auto_fill_button)

        btn_hlayout = QHBoxLayout()

        self.parse_button = PushButton(FIF.SEARCH, "解析头部", self)
        self.parse_button.setToolTip("从打包固件文件解析头部信息")
        self.parse_button.clicked.connect(self._parse_header)
        btn_hlayout.addWidget(self.parse_button)

        self.package_button = PushButton(FIF.SAVE, "打包固件", self)
        self.package_button.setToolTip("将头部、盐值、加密固件和签名打包为完整固件")
        self.package_button.clicked.connect(self._package_firmware)
        btn_hlayout.addWidget(self.package_button)

        self.verify_button = PushButton(FIF.CHECKBOX, "验证签名", self)
        self.verify_button.setToolTip("验证打包固件的HMAC头部校验和Ed25519签名")
        self.verify_button.clicked.connect(self._verify_firmware)
        btn_hlayout.addWidget(self.verify_button)

        operations_layout.addLayout(btn_hlayout)

        self.backup_checkbox = CheckBox("写入前备份原文件", self)
        self.backup_checkbox.setChecked(True)
        operations_layout.addWidget(self.backup_checkbox)

        self.operations_group.setLayout(operations_layout)
        self.header_setting_vBoxLayout.addWidget(self.operations_group)

    def _init_output_bar_ui(self):
        self.right_vBoxLayout = QVBoxLayout()
        self.right_vBoxLayout.setSpacing(0)
        self.right_vBoxLayout.setContentsMargins(10, 30, 30, 30)

        self.output_bar_widget = QWidget()
        self.output_bar_vBoxLayout = QVBoxLayout(self.output_bar_widget)
        self.output_bar_vBoxLayout.setContentsMargins(0, 0, 0, 0)

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
        bg_color = "rgb(39, 39, 39)" if is_dark else "rgb(249, 249, 249)"

        self.scroll_content.setStyleSheet(f"""
            QWidget#scroll_content {{
                background-color: {bg_color};
            }}
        """)

        self.scroll_area.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background-color: {bg_color};
            }}
        """)

        widgets_to_update = [
            getattr(self, 'file_group', None),
            getattr(self, 'editor_group', None),
            getattr(self, 'hkdf_group', None),
            getattr(self, 'ed25519_group', None),
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
            "选择加密固件文件",
            "",
            "加密固件 (*.bin.aes *.aes *.enc);;固件文件 (*.bin);;所有文件 (*.*)"
        )
        if file_path:
            self.input_file_lineedit.setText(file_path)
            self._log(f"已选择加密固件文件: {file_path}")

            file_size = os.path.getsize(file_path)
            if file_size > IV_SIZE:
                payload_size = DYNAMICSALT_SIZE + file_size
                self.payload_size_lineedit.setText(f"{payload_size:,} 字节")
                self.header.total_payload_size = payload_size
            else:
                self.payload_size_lineedit.setText("文件过小")
                self._log("警告: 文件太小，无法包含有效的IV和密文")

            if not self.output_file_lineedit.text():
                base, ext = os.path.splitext(file_path)
                if ext == '.aes':
                    base2, ext2 = os.path.splitext(base)
                    self.output_file_lineedit.setText(f"{base2}.iap.bin")
                else:
                    self.output_file_lineedit.setText(f"{base}.iap.bin")

    def _browse_output_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择打包固件文件",
            "",
            "IAP固件 (*.iap.bin *.bin);;所有文件 (*.*)"
        )
        if file_path:
            self.output_file_lineedit.setText(file_path)
            self._log(f"打包输出文件: {file_path}")

    def _set_current_timestamp(self):
        timestamp = int(datetime.now().timestamp())
        self.header.build_timestamp = timestamp
        self.timestamp_lineedit.setText(self.header.get_timestamp_string())
        self._log(f"已设置时间戳: {self.header.get_timestamp_string()}")

    def _generate_devkey(self):
        devkey = os.urandom(16)
        self.devkey_lineedit.setText(devkey.hex())
        InfoBar.success(
            title="DevKey生成",
            content="已生成随机128位DevKey",
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=2000,
            parent=self,
        )

    def _generate_dynamicsalt(self):
        dynamicsalt = os.urandom(16)
        self.dynamicsalt_lineedit.setText(dynamicsalt.hex())
        InfoBar.success(
            title="DynamicSalt生成",
            content="已生成随机128位DynamicSalt，将写入载荷前导",
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=2000,
            parent=self,
        )

    def _derive_hkdf_key(self):
        if not CRYPTO_AVAILABLE:
            InfoBar.error(
                title="错误",
                content="pycryptodome库未安装",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        devkey_hex = self.devkey_lineedit.text().strip()
        uid_hex = self.uid_lineedit.text().strip()
        dynamicsalt_hex = self.dynamicsalt_lineedit.text().strip()

        if not devkey_hex or not uid_hex or not dynamicsalt_hex:
            InfoBar.warning(
                title="警告",
                content="请先填写 DevKey、UID 和 DynamicSalt",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        try:
            devkey = bytes.fromhex(devkey_hex)
            uid = bytes.fromhex(uid_hex)
            dynamicsalt = bytes.fromhex(dynamicsalt_hex)

            if len(devkey) != 16:
                raise ValueError("DevKey长度必须为16字节")
            if len(uid) != 12:
                raise ValueError("UID长度必须为12字节")
            if len(dynamicsalt) != 16:
                raise ValueError("DynamicSalt长度必须为16字节")

            prk = hkdf_extract(salt=dynamicsalt, ikm=devkey)
            aes_key = hkdf_expand(prk=prk, info=uid, length=32)

            self._log("=" * 60)
            self._log("HKDF 两阶段密钥派生 (仅参考):")
            self._log(f"  DevKey:  {devkey_hex}")
            self._log(f"  UID:     {uid_hex}")
            self._log(f"  Salt:    {dynamicsalt_hex}")
            self._log(f"  PRK:     {prk.hex()}")
            self._log(f"  AES-Key: {aes_key.hex()}")
            self._log("=" * 60)

            InfoBar.success(
                title="HKDF派生成功",
                content=f"AES密钥: {aes_key.hex()[:16]}...",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
        except Exception as e:
            InfoBar.error(
                title="HKDF派生失败",
                content=str(e),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )

    def _pem_to_hex(self, pem_str):
        pem_content = pem_str.replace('\n', '')
        pem_content = pem_content.replace('-----BEGIN PRIVATE KEY-----', '')
        pem_content = pem_content.replace('-----END PRIVATE KEY-----', '')
        der_bytes = base64.b64decode(pem_content)
        if len(der_bytes) == 48:
            return der_bytes[16:48].hex()
        return der_bytes.hex()

    def _raw_to_pem(self, raw_bytes):
        header = b'\x30\x2e\x02\x01\x00\x30\x05\x06\x03\x2b\x65\x70\x04\x22\x04\x20'
        der_bytes = header + raw_bytes
        pem_content = base64.b64encode(der_bytes).decode('utf-8')
        pem_lines = [pem_content[i:i+64] for i in range(0, len(pem_content), 64)]
        return '-----BEGIN PRIVATE KEY-----\n' + '\n'.join(pem_lines) + '\n-----END PRIVATE KEY-----\n'

    def _generate_ed25519_key(self):
        if not CRYPTO_AVAILABLE:
            InfoBar.error(
                title="错误",
                content="pycryptodome库未安装",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        try:
            private_key = ECC.generate(curve='ed25519')
            self.ed25519_private_key_pem = private_key.export_key(format='PEM')
            public_key = private_key.public_key()
            self.public_key_bytes = public_key.export_key(format='raw')

            private_hex = self._pem_to_hex(self.ed25519_private_key_pem)
            self.private_key_lineedit.setText(private_hex)
            self.public_key_lineedit.setText(self.public_key_bytes.hex())

            self._log("Ed25519密钥对生成成功")
            self._log(f"  私钥: {private_hex}")
            self._log(f"  公钥: {self.public_key_bytes.hex()}")

            InfoBar.success(
                title="密钥生成成功",
                content="Ed25519密钥对已生成",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
        except Exception as e:
            self._log(f"密钥生成失败: {str(e)}")
            InfoBar.error(
                title="生成失败",
                content=str(e),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )

    def _load_ed25519_key(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "加载Ed25519私钥", "",
            "私钥文件 (*.key *.pem *.bin);;所有文件 (*)"
        )
        if file_path:
            try:
                with open(file_path, 'rb') as f:
                    data = f.read()

                if len(data) == 64:
                    self.ed25519_private_key_pem = self._raw_to_pem(
                        bytes.fromhex(data.decode('utf-8').strip())
                    )
                elif len(data) == 32:
                    self.ed25519_private_key_pem = self._raw_to_pem(data)
                else:
                    pem_str = data.decode('utf-8')
                    if '-----BEGIN PRIVATE KEY-----' in pem_str:
                        self.ed25519_private_key_pem = pem_str
                    else:
                        raise ValueError("无效的私钥格式")

                private_key = ECC.import_key(self.ed25519_private_key_pem)
                public_key = private_key.public_key()
                self.public_key_bytes = public_key.export_key(format='raw')

                private_hex = self._pem_to_hex(self.ed25519_private_key_pem)
                self.private_key_lineedit.setText(private_hex)
                self.public_key_lineedit.setText(self.public_key_bytes.hex())

                self._log(f"Ed25519私钥加载成功: {file_path}")

                InfoBar.success(
                    title="加载成功",
                    content="Ed25519私钥已加载",
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=3000,
                    parent=self,
                )
            except Exception as e:
                self._log(f"私钥加载失败: {str(e)}")
                InfoBar.error(
                    title="加载失败",
                    content=str(e),
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=3000,
                    parent=self,
                )

    def _auto_fill(self):
        input_file = self.input_file_lineedit.text().strip()
        if not input_file or not os.path.exists(input_file):
            InfoBar.warning(
                title="警告",
                content="请先选择有效的加密固件文件",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        file_size = os.path.getsize(input_file)
        if file_size > IV_SIZE:
            payload_size = DYNAMICSALT_SIZE + file_size
            self.header.total_payload_size = payload_size
            self.payload_size_lineedit.setText(f"{payload_size:,} 字节")
            self._log(f"载荷总大小: {payload_size} 字节 (Salt{DYNAMICSALT_SIZE} + IV{IV_SIZE} + 密文{file_size - IV_SIZE})")

        self._set_current_timestamp()

        if not self.dynamicsalt_lineedit.text().strip():
            self._generate_dynamicsalt()

        self._log("自动填充完成")

    def _get_header_from_ui(self):
        header = FirmwareHeader()

        header.magic = FIRMWARE_MAGIC
        header.header_version = self.header_ver_spinbox.value()
        header.firmware_version_major = self.major_spinbox.value()
        header.firmware_version_minor = self.minor_spinbox.value()
        header.firmware_version_patch = self.patch_spinbox.value()
        header.total_payload_size = self.header.total_payload_size
        header.image_type = self.image_type_combo.currentIndex() + 1
        header.encryption_algorithm = self.encryption_combo.currentIndex()
        header.signature_algorithm = self.signature_combo.currentIndex()

        hw_compat_hex = self.hw_compat_lineedit.text().strip()
        if hw_compat_hex:
            try:
                header.hardware_compatibility = int(hw_compat_hex, 16) & 0xFFFFFFFF
            except ValueError:
                header.hardware_compatibility = 0

        security_counter_hex = self.security_counter_lineedit.text().strip()
        if security_counter_hex:
            try:
                header.security_counter = int(security_counter_hex, 16) & 0xFFFFFFFF
            except ValueError:
                header.security_counter = 0

        header.build_timestamp = self.header.build_timestamp
        header.reserved = bytes(5)

        return header

    def _set_ui_from_header(self, header):
        self.header_ver_spinbox.setValue(header.header_version)
        self.major_spinbox.setValue(header.firmware_version_major)
        self.minor_spinbox.setValue(header.firmware_version_minor)
        self.patch_spinbox.setValue(header.firmware_version_patch)
        self.payload_size_lineedit.setText(f"{header.total_payload_size:,} 字节")
        self.timestamp_lineedit.setText(header.get_timestamp_string())

        image_type_idx = max(0, header.image_type - 1)
        if image_type_idx < self.image_type_combo.count():
            self.image_type_combo.setCurrentIndex(image_type_idx)

        if header.encryption_algorithm < self.encryption_combo.count():
            self.encryption_combo.setCurrentIndex(header.encryption_algorithm)

        if header.signature_algorithm < self.signature_combo.count():
            self.signature_combo.setCurrentIndex(header.signature_algorithm)

        self.hw_compat_lineedit.setText(f"{header.hardware_compatibility:08X}")
        self.security_counter_lineedit.setText(f"{header.security_counter:08X}")

        self.header = header

    def _parse_header(self):
        parse_file = self.output_file_lineedit.text().strip()
        if not parse_file:
            parse_file = self.input_file_lineedit.text().strip()
        
        if not parse_file:
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

        if not os.path.exists(parse_file):
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
            file_size = os.path.getsize(parse_file)
            with open(parse_file, 'rb') as f:
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

            self._log("=" * 60)
            self._log("头部解析成功:")
            self._log(f"  魔术字:           {header.magic}")
            self._log(f"  头部版本:         {header.header_version}")
            self._log(f"  固件版本:         {header.get_version_string()}")
            self._log(f"  载荷总大小:       {header.total_payload_size} 字节 (Salt+IV+密文)")
            self._log(f"  镜像类型:         {header.get_image_type_string()}")
            self._log(f"  加密算法:         {header.get_encryption_string()}")
            self._log(f"  签名算法:         {header.get_signature_string()}")
            self._log(f"  硬件兼容标识:     0x{header.hardware_compatibility:08X}")
            self._log(f"  安全计数器:       0x{header.security_counter:08X}")
            self._log(f"  构建时间戳:       {header.get_timestamp_string()}")
            self._log(f"  头部校验和:       {header.header_checksum.hex()}")
            self._log(f"  魔术字验证:       {'通过' if header.validate_magic() else '失败'}")

            remaining = file_size - HEADER_SIZE
            if header.total_payload_size > 0 and remaining >= DYNAMICSALT_SIZE + IV_SIZE:
                with open(parse_file, 'rb') as f:
                    f.seek(HEADER_SIZE)
                    dynamic_salt = f.read(DYNAMICSALT_SIZE)
                    iv = f.read(IV_SIZE)

                self.dynamicsalt_lineedit.setText(dynamic_salt.hex())

                encrypted_size = header.total_payload_size - DYNAMICSALT_SIZE - IV_SIZE
                self._log(f"  DynamicSalt:      {dynamic_salt.hex()}")
                self._log(f"  IV:               {iv.hex()}")
                self._log(f"  密文大小:         {encrypted_size} 字节")

                sig_offset = HEADER_SIZE + header.total_payload_size
                if file_size >= sig_offset + SIGNATURE_SIZE:
                    with open(parse_file, 'rb') as f:
                        f.seek(sig_offset)
                        signature = f.read(SIGNATURE_SIZE)
                    self._log(f"  Ed25519签名:      {signature.hex()}")
                else:
                    self._log("  Ed25519签名:      未找到")

            self._log("=" * 60)

            InfoBar.success(
                title="解析成功",
                content=f"固件版本: {header.get_version_string()}",
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

    def _package_firmware(self):
        if not CRYPTO_AVAILABLE:
            InfoBar.error(
                title="错误",
                content="pycryptodome库未安装，请使用 'pip install pycryptodome' 安装",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        input_file = self.input_file_lineedit.text().strip()
        if not input_file or not os.path.exists(input_file):
            InfoBar.warning(
                title="警告",
                content="请先选择有效的加密固件文件",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        output_file = self.output_file_lineedit.text().strip()
        if not output_file:
            base, ext = os.path.splitext(input_file)
            if ext == '.aes':
                base2, _ = os.path.splitext(base)
                output_file = f"{base2}.iap.bin"
            else:
                output_file = f"{base}.iap.bin"
            self.output_file_lineedit.setText(output_file)

        devkey_hex = self.devkey_lineedit.text().strip()
        if not devkey_hex:
            InfoBar.warning(
                title="警告",
                content="请输入DevKey（用于HMAC-SHA256头部校验和）",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        try:
            devkey = bytes.fromhex(devkey_hex)
            if len(devkey) != 16:
                raise ValueError("DevKey长度必须为16字节（32个十六进制字符）")
        except ValueError as e:
            InfoBar.warning(
                title="错误",
                content=f"DevKey格式错误: {str(e)}",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        dynamicsalt_hex = self.dynamicsalt_lineedit.text().strip()
        if not dynamicsalt_hex:
            InfoBar.warning(
                title="警告",
                content="请生成或输入DynamicSalt",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        try:
            dynamic_salt = bytes.fromhex(dynamicsalt_hex)
            if len(dynamic_salt) != 16:
                raise ValueError("DynamicSalt长度必须为16字节")
        except ValueError as e:
            InfoBar.warning(
                title="错误",
                content=f"DynamicSalt格式错误: {str(e)}",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        if not self.ed25519_private_key_pem:
            InfoBar.warning(
                title="警告",
                content="请先生成或加载Ed25519私钥",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        try:
            with open(input_file, 'rb') as f:
                aes_data = f.read()

            encryption_algo = self.encryption_combo.currentIndex()
            if encryption_algo != 0:
                if len(aes_data) < IV_SIZE:
                    raise ValueError("加密固件文件太小，无法包含IV")
                iv = aes_data[:IV_SIZE]
                encrypted_data = aes_data[IV_SIZE:]
            else:
                iv = bytes(IV_SIZE)
                encrypted_data = aes_data

            header = self._get_header_from_ui()
            header.total_payload_size = DYNAMICSALT_SIZE + len(iv) + len(encrypted_data)
            header.compute_checksum(devkey)

            if self.backup_checkbox.isChecked() and output_file == input_file:
                backup_file = input_file + ".bak"
                import shutil
                shutil.copy2(input_file, backup_file)
                self._log(f"已备份原文件到: {backup_file}")

            self._log("=" * 60)
            self._log("开始打包固件...")
            self._log(f"  输入文件:     {input_file}")
            self._log(f"  输出文件:     {output_file}")
            self._log(f"  头部:         {HEADER_SIZE} 字节")
            self._log(f"  DynamicSalt:  {dynamic_salt.hex()}")
            self._log(f"  IV:           {iv.hex()}")
            self._log(f"  密文大小:     {len(encrypted_data)} 字节")
            self._log(f"  载荷总大小:   {header.total_payload_size} 字节")
            self._log(f"  头部校验和:   {header.header_checksum.hex()}")
            self._log("=" * 60)

            self.package_button.setEnabled(False)
            self.parse_button.setEnabled(False)

            self.package_thread = PackageThread(
                header=header,
                dynamic_salt=dynamic_salt,
                iv=iv,
                encrypted_data=encrypted_data,
                ed25519_private_key_pem=self.ed25519_private_key_pem,
                output_path=output_file
            )
            self.package_thread.progress_updated.connect(self._on_package_progress)
            self.package_thread.package_completed.connect(self._on_package_completed)
            self.package_thread.error_occurred.connect(self._on_package_error)
            self.package_thread.start()

        except Exception as e:
            self._log(f"打包失败: {str(e)}")
            InfoBar.error(
                title="打包失败",
                content=str(e),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )

    def _on_package_progress(self, value):
        pass

    def _on_package_completed(self, success, message):
        self.package_button.setEnabled(True)
        self.parse_button.setEnabled(True)
        self._log(message)

        if success:
            InfoBar.success(
                title="打包成功",
                content="固件已成功打包",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )

    def _on_package_error(self, error):
        self.package_button.setEnabled(True)
        self.parse_button.setEnabled(True)
        self._log(f"错误: {error}")
        InfoBar.error(
            title="打包失败",
            content=error,
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=3000,
            parent=self,
        )

    def _verify_firmware(self):
        if not CRYPTO_AVAILABLE:
            InfoBar.error(
                title="错误",
                content="pycryptodome库未安装",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        verify_file = self.output_file_lineedit.text().strip()
        if not verify_file:
            verify_file = self.input_file_lineedit.text().strip()
        
        if not verify_file or not os.path.exists(verify_file):
            InfoBar.warning(
                title="警告",
                content="请先选择打包固件文件",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        try:
            with open(verify_file, 'rb') as f:
                all_data = f.read()

            if len(all_data) < HEADER_SIZE + SIGNATURE_SIZE:
                raise ValueError("文件太小，无法验证")

            header_data = all_data[:HEADER_SIZE]
            header = FirmwareHeader.from_bytes(header_data)

            self._log("=" * 60)
            self._log("验证固件签名...")

            devkey_hex = self.devkey_lineedit.text().strip()
            if devkey_hex:
                try:
                    devkey = bytes.fromhex(devkey_hex)
                    if header.verify_checksum(devkey):
                        self._log("  HMAC-SHA256头部校验: ✓ 通过")
                    else:
                        self._log("  HMAC-SHA256头部校验: ✗ 失败 (DevKey不匹配或头部被篡改)")
                except:
                    self._log("  HMAC-SHA256头部校验: 跳过 (DevKey格式错误)")
            else:
                self._log("  HMAC-SHA256头部校验: 跳过 (未提供DevKey)")

            if self.public_key_bytes and header.signature_algorithm == 0x01:
                payload = all_data[HEADER_SIZE:HEADER_SIZE + header.total_payload_size]
                signature = all_data[HEADER_SIZE + header.total_payload_size:
                                     HEADER_SIZE + header.total_payload_size + SIGNATURE_SIZE]

                if len(signature) != SIGNATURE_SIZE:
                    self._log("  Ed25519签名验证: ✗ 签名长度错误")
                else:
                    try:
                        data_to_verify = header_data + payload
                        header_der = b'\x30\x2a\x30\x05\x06\x03\x2b\x65\x70\x03\x21\x00'
                        der_bytes = header_der + self.public_key_bytes
                        pem_content = base64.b64encode(der_bytes).decode('utf-8')
                        public_pem = ('-----BEGIN PUBLIC KEY-----\n' +
                                      pem_content + '\n-----END PUBLIC KEY-----\n')
                        public_key = ECC.import_key(public_pem)

                        verifier = eddsa.new(public_key, 'rfc8032')
                        hash_obj = SHA512.new(data_to_verify)
                        verifier.verify(hash_obj.digest(), signature)

                        self._log("  Ed25519签名验证:   ✓ 通过")
                    except ValueError:
                        self._log("  Ed25519签名验证:   ✗ 失败 (签名无效或固件被篡改)")
                    except Exception as e:
                        self._log(f"  Ed25519签名验证:   ✗ 失败 ({str(e)})")
            elif header.signature_algorithm == 0x01:
                self._log("  Ed25519签名验证:   跳过 (未加载公钥)")
            else:
                self._log("  Ed25519签名验证:   跳过 (无签名)")

            self._log("=" * 60)

            InfoBar.success(
                title="验证完成",
                content="请查看日志了解详细结果",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )

        except Exception as e:
            self._log(f"验证失败: {str(e)}")
            InfoBar.error(
                title="验证失败",
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
