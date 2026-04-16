# coding:utf-8
import sys
import os
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFileDialog,
    QGroupBox,
)

from qfluentwidgets import (
    FluentIcon as FIF,
    InfoBar,
    InfoBarPosition,
    BodyLabel,
    StrongBodyLabel,
    PushButton,
    ComboBox,
    LineEdit,
    CheckBox,
    ProgressBar,
    PlainTextEdit,
    isDarkTheme,
)
from settings.config import cfg

try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad, unpad
    from Crypto.Protocol.KDF import HKDF
    from Crypto.Hash import SHA256
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False


class AES_Encrypt_Thread(QThread):
    progress_updated = pyqtSignal(int, int)
    encryption_completed = pyqtSignal(bool, str, str)
    error_occurred = pyqtSignal(str)

    def __init__(self, input_file, output_file, key, iv=None, mode='CBC'):
        super().__init__()
        self.input_file = input_file
        self.output_file = output_file
        self.key = key
        self.iv = iv
        self.mode = mode

    def run(self):
        if not CRYPTO_AVAILABLE:
            self.error_occurred.emit("pycryptodome库未安装，请使用 'pip install pycryptodome' 安装")
            return

        try:
            file_size = os.path.getsize(self.input_file)
            chunk_size = 4096
            total_chunks = (file_size + chunk_size - 1) // chunk_size

            with open(self.input_file, 'rb') as f_in:
                data = f_in.read()

            if self.mode == 'CBC':
                if self.iv is None:
                    self.iv = os.urandom(16)
                cipher = AES.new(self.key, AES.MODE_CBC, self.iv)
            elif self.mode == 'ECB':
                cipher = AES.new(self.key, AES.MODE_ECB)
            elif self.mode == 'CTR':
                if self.iv is None:
                    self.iv = os.urandom(16)
                cipher = AES.new(self.key, AES.MODE_CTR, nonce=self.iv[:8])
            elif self.mode == 'CFB':
                if self.iv is None:
                    self.iv = os.urandom(16)
                cipher = AES.new(self.key, AES.MODE_CFB, self.iv)
            elif self.mode == 'OFB':
                if self.iv is None:
                    self.iv = os.urandom(16)
                cipher = AES.new(self.key, AES.MODE_OFB, self.iv)
            else:
                self.error_occurred.emit(f"不支持的加密模式: {self.mode}")
                return

            encrypted_data = cipher.encrypt(pad(data, AES.block_size))

            with open(self.output_file, 'wb') as f_out:
                if self.mode in ['CBC', 'CFB', 'OFB']:
                    f_out.write(self.iv)
                f_out.write(encrypted_data)

            self.progress_updated.emit(100, 100)
            self.encryption_completed.emit(True, self.output_file, f"加密完成，输出文件: {self.output_file}")

        except Exception as e:
            self.error_occurred.emit(f"加密失败: {str(e)}")


class AES_Decrypt_Thread(QThread):
    progress_updated = pyqtSignal(int, int)
    decryption_completed = pyqtSignal(bool, str, str)
    error_occurred = pyqtSignal(str)

    def __init__(self, input_file, output_file, key, iv=None, mode='CBC'):
        super().__init__()
        self.input_file = input_file
        self.output_file = output_file
        self.key = key
        self.iv = iv
        self.mode = mode

    def run(self):
        if not CRYPTO_AVAILABLE:
            self.error_occurred.emit("pycryptodome库未安装，请使用 'pip install pycryptodome' 安装")
            return

        try:
            with open(self.input_file, 'rb') as f_in:
                data = f_in.read()

            if self.mode in ['CBC', 'CFB', 'OFB']:
                if self.iv is None:
                    self.iv = data[:16]
                data = data[16:]
            
            if self.mode == 'CBC':
                cipher = AES.new(self.key, AES.MODE_CBC, self.iv)
            elif self.mode == 'ECB':
                cipher = AES.new(self.key, AES.MODE_ECB)
            elif self.mode == 'CTR':
                cipher = AES.new(self.key, AES.MODE_CTR, nonce=self.iv[:8])
            elif self.mode == 'CFB':
                cipher = AES.new(self.key, AES.MODE_CFB, self.iv)
            elif self.mode == 'OFB':
                cipher = AES.new(self.key, AES.MODE_OFB, self.iv)
            else:
                self.error_occurred.emit(f"不支持的解密模式: {self.mode}")
                return

            decrypted_data = unpad(cipher.decrypt(data), AES.block_size)

            with open(self.output_file, 'wb') as f_out:
                f_out.write(decrypted_data)

            self.progress_updated.emit(100, 100)
            self.decryption_completed.emit(True, self.output_file, f"解密完成，输出文件: {self.output_file}")

        except Exception as e:
            self.error_occurred.emit(f"解密失败: {str(e)}")


class AES_Tools_Widget(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("aes_setting_widget")
        self.resize(1000, 700)
        self.Main_hLayout = QHBoxLayout(self)
        self.aes_setting_vBoxLayout = QVBoxLayout()
        
        self.init_ui()
        self.Main_hLayout.addLayout(self.aes_setting_vBoxLayout)
        self.init_output_bar_ui()
        
        self.encryption_thread = None
        self.decryption_thread = None
        
        self.__updateTheme()
        cfg.themeChanged.connect(self.__updateTheme)

    def init_ui(self):
        main_layout = QVBoxLayout()

        self.file_group = QGroupBox("固件文件")
        file_layout = QVBoxLayout()
        
        input_label = BodyLabel("输入文件:")
        self.input_file_lineedit = LineEdit()
        self.input_file_lineedit.setPlaceholderText("请选择要加密/解密的固件文件")
        self.browse_input_button = PushButton(FIF.FOLDER, "浏览", self)
        self.browse_input_button.clicked.connect(self.browse_input_file)
        input_hlayout = QHBoxLayout()
        input_hlayout.addWidget(input_label)
        input_hlayout.addWidget(self.input_file_lineedit, 1)
        input_hlayout.addWidget(self.browse_input_button)
        file_layout.addLayout(input_hlayout)

        output_label = BodyLabel("输出文件:")
        self.output_file_lineedit = LineEdit()
        self.output_file_lineedit.setPlaceholderText("加密/解密后的固件输出路径（可选）")
        self.browse_output_button = PushButton(FIF.FOLDER, "浏览", self)
        self.browse_output_button.clicked.connect(self.browse_output_file)
        output_hlayout = QHBoxLayout()
        output_hlayout.addWidget(output_label)
        output_hlayout.addWidget(self.output_file_lineedit, 1)
        output_hlayout.addWidget(self.browse_output_button)
        file_layout.addLayout(output_hlayout)

        suffix_label = BodyLabel("输出后缀:")
        self.suffix_combo = ComboBox()
        self.suffix_combo.addItems([".aes", ".bin", ".bin.aes", ".enc", ".encrypted"])
        self.suffix_combo.setCurrentIndex(2)
        self.suffix_combo.setFixedWidth(120)
        suffix_hlayout = QHBoxLayout()
        suffix_hlayout.addWidget(suffix_label)
        suffix_hlayout.addStretch(1)
        suffix_hlayout.addWidget(self.suffix_combo)
        suffix_hlayout.setContentsMargins(0, 2, 0, 2)
        file_layout.addLayout(suffix_hlayout)

        self.file_group.setLayout(file_layout)
        main_layout.addWidget(self.file_group)

        self.key_group = QGroupBox("加密设置")
        key_layout = QVBoxLayout()

        mode_label = BodyLabel("加密模式:")
        self.mode_combo = ComboBox()
        self.mode_combo.addItems(["CBC", "ECB", "CTR", "CFB", "OFB"])
        self.mode_combo.setCurrentIndex(0)
        self.mode_combo.setFixedWidth(120)
        self.mode_combo.currentTextChanged.connect(self.on_mode_changed)
        mode_hlayout = QHBoxLayout()
        mode_hlayout.addWidget(mode_label)
        mode_hlayout.addStretch(1)
        mode_hlayout.addWidget(self.mode_combo)
        mode_hlayout.setContentsMargins(0, 2, 0, 2)
        key_layout.addLayout(mode_hlayout)

        key_label = BodyLabel("密钥 (32字节):")
        self.key_lineedit = LineEdit()
        self.key_lineedit.setPlaceholderText("32字节密钥（64个十六进制字符）")
        self.generate_key_button = PushButton(FIF.SYNC, "生成", self)
        self.generate_key_button.clicked.connect(self.generate_key)
        key_hlayout = QHBoxLayout()
        key_hlayout.addWidget(key_label)
        key_hlayout.addWidget(self.key_lineedit, 1)
        key_hlayout.addWidget(self.generate_key_button)
        key_hlayout.setContentsMargins(0, 2, 0, 2)
        key_layout.addLayout(key_hlayout)

        self.iv_label = BodyLabel("IV向量 (16字节):")
        self.iv_lineedit = LineEdit()
        self.iv_lineedit.setPlaceholderText("16字节IV（32个十六进制字符），加密留空自动生成，解密留空从文件读取")
        self.generate_iv_button = PushButton(FIF.SYNC, "生成", self)
        self.generate_iv_button.clicked.connect(self.generate_iv)
        iv_hlayout = QHBoxLayout()
        iv_hlayout.addWidget(self.iv_label)
        iv_hlayout.addWidget(self.iv_lineedit, 1)
        iv_hlayout.addWidget(self.generate_iv_button)
        iv_hlayout.setContentsMargins(0, 2, 0, 2)
        key_layout.addLayout(iv_hlayout)

        self.save_key_checkbox = CheckBox("保存密钥和IV到文件", self)
        self.save_key_checkbox.setChecked(True)
        key_layout.addWidget(self.save_key_checkbox)

        self.key_group.setLayout(key_layout)
        main_layout.addWidget(self.key_group)

        self.hkdf_group = QGroupBox("HKDF密钥派生 (可选)")
        hkdf_layout = QVBoxLayout()

        uid_label = BodyLabel("芯片UID (96位):")
        self.uid_lineedit = LineEdit()
        self.uid_lineedit.setPlaceholderText("96位UID（24个十六进制字符），例如：123456789ABCDEF012345678")
        uid_hlayout = QHBoxLayout()
        uid_hlayout.addWidget(uid_label)
        uid_hlayout.addWidget(self.uid_lineedit, 1)
        uid_hlayout.setContentsMargins(0, 2, 0, 2)
        hkdf_layout.addLayout(uid_hlayout)

        salt_label = BodyLabel("Salt (可选):")
        self.salt_lineedit = LineEdit()
        self.salt_lineedit.setPlaceholderText("Salt值（十六进制字符串），留空则使用默认salt")
        self.generate_salt_button = PushButton(FIF.SYNC, "生成", self)
        self.generate_salt_button.clicked.connect(self.generate_salt)
        salt_hlayout = QHBoxLayout()
        salt_hlayout.addWidget(salt_label)
        salt_hlayout.addWidget(self.salt_lineedit, 1)
        salt_hlayout.addWidget(self.generate_salt_button)
        salt_hlayout.setContentsMargins(0, 2, 0, 2)
        hkdf_layout.addLayout(salt_hlayout)

        self.hkdf_button = PushButton(FIF.CERTIFICATE, "使用HKDF生成密钥", self)
        self.hkdf_button.clicked.connect(self.generate_key_from_hkdf)
        hkdf_layout.addWidget(self.hkdf_button)

        self.hkdf_group.setLayout(hkdf_layout)
        main_layout.addWidget(self.hkdf_group)

        self.progress_group = QGroupBox("进度")
        progress_layout = QVBoxLayout()
        
        self.progress_bar = ProgressBar(self)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(8)
        progress_layout.addWidget(self.progress_bar)
        
        self.progress_label = BodyLabel("准备就绪")
        progress_layout.addWidget(self.progress_label)
        
        self.progress_group.setLayout(progress_layout)
        main_layout.addWidget(self.progress_group)

        button_hlayout = QHBoxLayout()
        self.encrypt_button = PushButton(FIF.FINGERPRINT, "执行加密", self)
        self.encrypt_button.clicked.connect(self.execute_encryption)
        button_hlayout.addWidget(self.encrypt_button)
        
        self.decrypt_button = PushButton(FIF.IOT, "执行解密", self)
        self.decrypt_button.clicked.connect(self.execute_decryption)
        button_hlayout.addWidget(self.decrypt_button)
        
        main_layout.addLayout(button_hlayout)

        main_layout.setSpacing(12)
        self.aes_setting_vBoxLayout.addLayout(main_layout)
        self.aes_setting_vBoxLayout.addStretch(1)

    def init_output_bar_ui(self):
        self.right_vBoxLayout = QVBoxLayout()
        self.right_vBoxLayout.setSpacing(0)
        self.right_vBoxLayout.setContentsMargins(0, 0, 0, 0)

        self.output_bar_widget = QWidget()
        self.output_bar_vBoxLayout = QVBoxLayout(self.output_bar_widget)

        self.output_area_text = PlainTextEdit()
        self.output_area_text.setReadOnly(True)
        self.output_bar_vBoxLayout.addWidget(self.output_area_text)

        self.output_bar_button_hLayout = QHBoxLayout()

        self.clear_output_button = PushButton(FIF.DELETE, "清空输出", self)
        self.clear_output_button.clicked.connect(self.clear_output)
        self.output_bar_button_hLayout.addWidget(self.clear_output_button)

        self.output_bar_button_hLayout.addStretch(1)

        self.export_output_button = PushButton(FIF.SAVE, "导出输出", self)
        self.export_output_button.clicked.connect(self.export_output)
        self.output_bar_button_hLayout.addWidget(self.export_output_button)

        self.output_bar_vBoxLayout.addLayout(self.output_bar_button_hLayout)
        self.output_bar_vBoxLayout.setSpacing(10)
        self.output_bar_vBoxLayout.setContentsMargins(0, 0, 0, 9)

        self.right_vBoxLayout.addWidget(self.output_bar_widget, 5)
        self.Main_hLayout.addLayout(self.right_vBoxLayout, 1)

    def __updateTheme(self):
        is_dark = isDarkTheme()
        text_color = "#ffffff" if is_dark else "#000000"
        
        widgets_to_update = [
            getattr(self, 'file_group', None),
            getattr(self, 'key_group', None),
            getattr(self, 'hkdf_group', None),
            getattr(self, 'progress_group', None),
        ]
        
        for widget in widgets_to_update:
            if widget:
                widget.setStyleSheet(f"color: {text_color};")

    def on_mode_changed(self, mode):
        if mode == 'ECB':
            self.iv_lineedit.setEnabled(False)
            self.generate_iv_button.setEnabled(False)
        else:
            self.iv_lineedit.setEnabled(True)
            self.generate_iv_button.setEnabled(True)

    def browse_input_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择固件文件",
            "",
            "固件文件 (*.bin *.hex *.elf *.aes *.enc);;所有文件 (*.*)"
        )
        if file_path:
            self.input_file_lineedit.setText(file_path)
            if not self.output_file_lineedit.text():
                base, ext = os.path.splitext(file_path)
                suffix = self.suffix_combo.currentText()
                self.output_file_lineedit.setText(f"{base}{suffix}")

    def browse_output_file(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "选择输出文件",
            "",
            "固件文件 (*.bin *.aes);;所有文件 (*.*)"
        )
        if file_path:
            self.output_file_lineedit.setText(file_path)

    def generate_key(self):
        key = os.urandom(32)
        self.key_lineedit.setText(key.hex())
        InfoBar.success(
            title="密钥生成",
            content="已生成随机AES-256密钥",
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=2000,
            parent=self,
        )

    def generate_iv(self):
        iv = os.urandom(16)
        self.iv_lineedit.setText(iv.hex())
        InfoBar.success(
            title="IV生成",
            content="已生成随机IV向量",
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=2000,
            parent=self,
        )

    def generate_salt(self):
        salt = os.urandom(16)
        self.salt_lineedit.setText(salt.hex())
        InfoBar.success(
            title="Salt生成",
            content="已生成随机Salt",
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=2000,
            parent=self,
        )

    def generate_key_from_hkdf(self):
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

        uid_hex = self.uid_lineedit.text().strip()
        if not uid_hex:
            InfoBar.warning(
                title="错误",
                content="请输入芯片UID",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        try:
            uid = bytes.fromhex(uid_hex)
            if len(uid) != 12:
                raise ValueError("UID长度必须为96位（12字节，24个十六进制字符）")
        except ValueError as e:
            InfoBar.warning(
                title="错误",
                content=f"UID格式错误: {str(e)}",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        salt_hex = self.salt_lineedit.text().strip()
        if salt_hex:
            try:
                salt = bytes.fromhex(salt_hex)
            except ValueError as e:
                InfoBar.warning(
                    title="错误",
                    content=f"Salt格式错误: {str(e)}",
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=3000,
                    parent=self,
                )
                return
        else:
            salt = b'IAP_HKDF_SALT_DEFAULT'

        try:
            key = HKDF(
                master=uid,
                salt=salt,
                key_len=32,
                hashmod=SHA256,
                num_keys=1
            )
            
            self.key_lineedit.setText(key.hex())
            
            InfoBar.success(
                title="HKDF密钥生成成功",
                content=f"已从UID派生出AES-256密钥",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            
            self.output_area_text.appendPlainText("HKDF密钥派生信息:")
            self.output_area_text.appendPlainText(f"UID: {uid_hex}")
            self.output_area_text.appendPlainText(f"Salt: {salt.hex()}")
            self.output_area_text.appendPlainText(f"派生密钥: {key.hex()}")
            self.output_area_text.appendPlainText(f"算法: HKDF-SHA256")
            
        except Exception as e:
            InfoBar.error(
                title="HKDF密钥生成失败",
                content=f"错误: {str(e)}",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )

    def clear_output(self):
        self.output_area_text.clear()

    def export_output(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出输出",
            "aes_output.txt",
            "文本文件 (*.txt);;所有文件 (*.*)"
        )
        if file_path:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(self.output_area_text.toPlainText())
            InfoBar.success(
                title="导出成功",
                content=f"输出已导出到 {file_path}",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )

    def execute_encryption(self):
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
        if not input_file:
            InfoBar.warning(
                title="错误",
                content="请选择输入文件",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        if not os.path.exists(input_file):
            InfoBar.warning(
                title="错误",
                content="输入文件不存在",
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
            suffix = self.suffix_combo.currentText()
            output_file = f"{base}{suffix}"
            self.output_file_lineedit.setText(output_file)

        key_hex = self.key_lineedit.text().strip()
        if not key_hex:
            InfoBar.warning(
                title="错误",
                content="请输入或生成密钥",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        try:
            key = bytes.fromhex(key_hex)
            if len(key) != 32:
                raise ValueError("密钥长度必须为32字节（64个十六进制字符）")
        except ValueError as e:
            InfoBar.warning(
                title="错误",
                content=f"密钥格式错误: {str(e)}",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        mode = self.mode_combo.currentText()
        iv = None
        
        if mode != 'ECB':
            iv_hex = self.iv_lineedit.text().strip()
            if iv_hex:
                try:
                    iv = bytes.fromhex(iv_hex)
                    if len(iv) != 16:
                        raise ValueError("IV长度必须为16字节（32个十六进制字符）")
                except ValueError as e:
                    InfoBar.warning(
                        title="错误",
                        content=f"IV格式错误: {str(e)}",
                        orient=Qt.Orientation.Horizontal,
                        isClosable=True,
                        position=InfoBarPosition.TOP,
                        duration=3000,
                        parent=self,
                    )
                    return

        self.output_area_text.clear()
        self.output_area_text.appendPlainText("=" * 74)
        self.output_area_text.appendPlainText("开始AES-256加密...")
        self.output_area_text.appendPlainText(f"输入文件: {input_file}")
        self.output_area_text.appendPlainText(f"输出文件: {output_file}")
        self.output_area_text.appendPlainText(f"加密模式: {mode}")
        self.output_area_text.appendPlainText(f"密钥长度: {len(key) * 8} bits")
        if iv:
            self.output_area_text.appendPlainText(f"IV长度: {len(iv) * 8} bits")

        self.progress_bar.setValue(0)
        self.progress_label.setText("正在加密...")

        self.encrypt_button.setEnabled(False)
        self.decrypt_button.setEnabled(False)
        self.encrypt_button.setText("加密中...")

        self.encryption_thread = AES_Encrypt_Thread(
            input_file=input_file,
            output_file=output_file,
            key=key,
            iv=iv,
            mode=mode
        )
        self.encryption_thread.progress_updated.connect(self.on_progress_updated)
        self.encryption_thread.encryption_completed.connect(self.on_encryption_completed)
        self.encryption_thread.error_occurred.connect(self.on_error_occurred)
        self.encryption_thread.start()

    def execute_decryption(self):
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
        if not input_file:
            InfoBar.warning(
                title="错误",
                content="请选择输入文件",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        if not os.path.exists(input_file):
            InfoBar.warning(
                title="错误",
                content="输入文件不存在",
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
            output_file = f"{base}_decrypted.bin"
            self.output_file_lineedit.setText(output_file)

        key_hex = self.key_lineedit.text().strip()
        if not key_hex:
            InfoBar.warning(
                title="错误",
                content="请输入密钥",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        try:
            key = bytes.fromhex(key_hex)
            if len(key) != 32:
                raise ValueError("密钥长度必须为32字节（64个十六进制字符）")
        except ValueError as e:
            InfoBar.warning(
                title="错误",
                content=f"密钥格式错误: {str(e)}",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        mode = self.mode_combo.currentText()
        iv = None
        
        if mode != 'ECB':
            iv_hex = self.iv_lineedit.text().strip()
            if iv_hex:
                try:
                    iv = bytes.fromhex(iv_hex)
                    if len(iv) != 16:
                        raise ValueError("IV长度必须为16字节（32个十六进制字符）")
                except ValueError as e:
                    InfoBar.warning(
                        title="错误",
                        content=f"IV格式错误: {str(e)}",
                        orient=Qt.Orientation.Horizontal,
                        isClosable=True,
                        position=InfoBarPosition.TOP,
                        duration=3000,
                        parent=self,
                    )
                    return

        self.output_area_text.clear()
        self.output_area_text.appendPlainText("=" * 74)
        self.output_area_text.appendPlainText("开始AES-256解密...")
        self.output_area_text.appendPlainText(f"输入文件: {input_file}")
        self.output_area_text.appendPlainText(f"输出文件: {output_file}")
        self.output_area_text.appendPlainText(f"解密模式: {mode}")
        self.output_area_text.appendPlainText(f"密钥长度: {len(key) * 8} bits")
        if iv:
            self.output_area_text.appendPlainText(f"IV长度: {len(iv) * 8} bits (使用提供的IV)")
        else:
            self.output_area_text.appendPlainText("IV: 将从加密文件中读取")

        self.progress_bar.setValue(0)
        self.progress_label.setText("正在解密...")

        self.encrypt_button.setEnabled(False)
        self.decrypt_button.setEnabled(False)
        self.decrypt_button.setText("解密中...")

        self.decryption_thread = AES_Decrypt_Thread(
            input_file=input_file,
            output_file=output_file,
            key=key,
            iv=iv,
            mode=mode
        )
        self.decryption_thread.progress_updated.connect(self.on_progress_updated)
        self.decryption_thread.decryption_completed.connect(self.on_decryption_completed)
        self.decryption_thread.error_occurred.connect(self.on_decryption_error_occurred)
        self.decryption_thread.start()

    def on_progress_updated(self, progress, total):
        self.progress_bar.setValue(progress)
        self.progress_label.setText(f"进度: {progress}%")

    def on_encryption_completed(self, success, output_file, message):
        if success:
            self.output_area_text.appendPlainText(message)
            self.progress_bar.setValue(100)
            self.progress_label.setText("加密完成")
            
            if self.save_key_checkbox.isChecked():
                key_file = output_file + ".key"
                iv_hex = self.iv_lineedit.text().strip()
                uid_hex = self.uid_lineedit.text().strip()
                salt_hex = self.salt_lineedit.text().strip()
                
                with open(key_file, 'w') as f:
                    f.write(f"Key: {self.key_lineedit.text().strip()}\n")
                    if iv_hex:
                        f.write(f"IV: {iv_hex}\n")
                    f.write(f"Mode: {self.mode_combo.currentText()}\n")
                    
                    if uid_hex:
                        f.write(f"UID: {uid_hex}\n")
                        f.write(f"Algorithm: HKDF-SHA256\n")
                    if salt_hex:
                        f.write(f"Salt: {salt_hex}\n")
                        
                self.output_area_text.appendPlainText(f"密钥文件已保存: {key_file}")
            
            InfoBar.success(
                title="加密成功",
                content=f"固件已成功加密",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
        else:
            self.output_area_text.appendPlainText("加密失败")
            self.progress_label.setText("加密失败")
            InfoBar.error(
                title="加密失败",
                content=message,
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
        
        self.encrypt_button.setEnabled(True)
        self.decrypt_button.setEnabled(True)
        self.encrypt_button.setText("执行加密")

    def on_decryption_completed(self, success, output_file, message):
        if success:
            self.output_area_text.appendPlainText(message)
            self.progress_bar.setValue(100)
            self.progress_label.setText("解密完成")
            
            InfoBar.success(
                title="解密成功",
                content=f"固件已成功解密",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
        else:
            self.output_area_text.appendPlainText("解密失败")
            self.progress_label.setText("解密失败")
            InfoBar.error(
                title="解密失败",
                content=message,
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
        
        self.encrypt_button.setEnabled(True)
        self.decrypt_button.setEnabled(True)
        self.decrypt_button.setText("执行解密")

    def on_error_occurred(self, error):
        self.output_area_text.appendPlainText(f"错误: {error}")
        self.progress_label.setText("加密失败")
        InfoBar.error(
            title="加密失败",
            content=error,
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=3000,
            parent=self,
        )
        self.encrypt_button.setEnabled(True)
        self.decrypt_button.setEnabled(True)
        self.encrypt_button.setText("执行加密")

    def on_decryption_error_occurred(self, error):
        self.output_area_text.appendPlainText(f"错误: {error}")
        self.progress_label.setText("解密失败")
        InfoBar.error(
            title="解密失败",
            content=error,
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=3000,
            parent=self,
        )
        self.encrypt_button.setEnabled(True)
        self.decrypt_button.setEnabled(True)
        self.decrypt_button.setText("执行解密")


if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    w = AES_Tools_Widget()
    w.show()
    sys.exit(app.exec())
