# coding:utf-8
import sys
import os
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
    QTabWidget,
)

from qfluentwidgets import (
    FluentIcon as FIF,
    InfoBar,
    InfoBarPosition,
    BodyLabel,
    StrongBodyLabel,
    PushButton,
    LineEdit,
    PlainTextEdit,
    isDarkTheme,
    ComboBox,
    CheckBox,
    ProgressBar,
)

from settings.config import cfg

try:
    from Crypto.PublicKey import ECC
    from Crypto.Signature import eddsa
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False


class SignThread(QThread):
    progress_updated = pyqtSignal(int)
    sign_completed = pyqtSignal(bool, str)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, file_path, private_key_pem, output_path=None):
        super().__init__()
        self.file_path = file_path
        self.private_key_pem = private_key_pem
        self.output_path = output_path
    
    def run(self):
        if not CRYPTO_AVAILABLE:
            self.error_occurred.emit("pycryptodome库未安装，请使用 'pip install pycryptodome' 安装")
            return
        
        try:
            self.progress_updated.emit(10)
            
            private_key = ECC.import_key(self.private_key_pem)
            
            self.progress_updated.emit(30)
            
            with open(self.file_path, 'rb') as f:
                data = f.read()
            
            self.progress_updated.emit(60)
            
            signer = eddsa.new(private_key, 'rfc8032')
            signature = signer.sign(data)
            
            self.progress_updated.emit(80)
            
            if self.output_path is None:
                self.output_path = self.file_path + ".sig"
            
            with open(self.output_path, 'wb') as f:
                f.write(signature)
            
            self.progress_updated.emit(100)
            
            self.sign_completed.emit(True, f"签名成功！\n签名文件: {self.output_path}\n签名长度: {len(signature)} 字节")
            
        except Exception as e:
            self.error_occurred.emit(f"签名失败: {str(e)}")


class VerifyThread(QThread):
    progress_updated = pyqtSignal(int)
    verify_completed = pyqtSignal(bool, str)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, file_path, signature_path, public_key_bytes):
        super().__init__()
        self.file_path = file_path
        self.signature_path = signature_path
        self.public_key_bytes = public_key_bytes
    
    def run(self):
        if not CRYPTO_AVAILABLE:
            self.error_occurred.emit("pycryptodome库未安装，请使用 'pip install pycryptodome' 安装")
            return
        
        try:
            self.progress_updated.emit(10)
            
            header = b'\x30\x2a\x30\x05\x06\x03\x2b\x65\x70\x03\x21\x00'
            der_bytes = header + self.public_key_bytes
            pem_content = base64.b64encode(der_bytes).decode('utf-8')
            public_pem = '-----BEGIN PUBLIC KEY-----\n' + pem_content + '\n-----END PUBLIC KEY-----\n'
            public_key = ECC.import_key(public_pem)
            
            self.progress_updated.emit(30)
            
            with open(self.signature_path, 'rb') as f:
                signature = f.read()
            
            self.progress_updated.emit(50)
            
            if len(signature) != 64:
                self.error_occurred.emit(f"签名长度错误，Ed25519签名应为64字节，实际为{len(signature)}字节")
                return
            
            with open(self.file_path, 'rb') as f:
                data = f.read()
            
            self.progress_updated.emit(80)
            
            verifier = eddsa.new(public_key, 'rfc8032')
            verifier.verify(data, signature)
            
            self.progress_updated.emit(100)
            
            self.verify_completed.emit(True, "签名验证成功！\n文件完整性验证通过，签名有效。")
            
        except ValueError:
            self.error_occurred.emit("签名验证失败！\n签名无效或文件已被篡改。")
        except Exception as e:
            self.error_occurred.emit(f"验证失败: {str(e)}")


class Ed25519_Widget(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("ed25519_widget")
        self.resize(1000, 700)
        
        self.Main_hLayout = QHBoxLayout(self)
        self.main_vBoxLayout = QVBoxLayout()
        self.main_vBoxLayout.setSpacing(10)
        self.main_vBoxLayout.setContentsMargins(30, 30, 30, 30)
        
        self.private_key_pem = None
        self.public_key_bytes = None
        
        self.sign_thread = None
        self.verify_thread = None
        
        self._init_key_management_ui()
        self._init_sign_ui()
        self._init_verify_ui()
        
        self.Main_hLayout.addLayout(self.main_vBoxLayout, 1)
        self._init_output_bar_ui()
        
        self.__updateTheme()
        cfg.themeChanged.connect(self.__updateTheme)
    
    def _pem_to_hex(self, pem_str):
        pem_content = pem_str.replace('\n', '')
        pem_content = pem_content.replace('-----BEGIN PRIVATE KEY-----', '')
        pem_content = pem_content.replace('-----END PRIVATE KEY-----', '')
        der_bytes = base64.b64decode(pem_content)
        if len(der_bytes) == 48:
            return der_bytes[16:48].hex()
        return der_bytes.hex()
    
    def _raw_public_to_pem(self, raw_bytes):
        header = b'\x30\x2a\x30\x05\x06\x03\x2b\x65\x70\x03\x21\x00'
        der_bytes = header + raw_bytes
        pem_content = base64.b64encode(der_bytes).decode('utf-8')
        pem_lines = [pem_content[i:i+64] for i in range(0, len(pem_content), 64)]
        return '-----BEGIN PUBLIC KEY-----\n' + '\n'.join(pem_lines) + '\n-----END PUBLIC KEY-----\n'
    
    def _init_key_management_ui(self):
        self.key_group = QGroupBox("密钥管理")
        key_layout = QVBoxLayout()
        key_layout.setSpacing(12)
        
        generate_title = StrongBodyLabel("生成密钥对")
        key_layout.addWidget(generate_title)
        
        generate_btn_layout = QHBoxLayout()
        self.generate_key_button = PushButton(FIF.CERTIFICATE, "生成Ed25519密钥对", self)
        self.generate_key_button.clicked.connect(self._generate_key_pair)
        generate_btn_layout.addWidget(self.generate_key_button)
        generate_btn_layout.addStretch(1)
        key_layout.addLayout(generate_btn_layout)
        
        private_key_label = BodyLabel("私钥 (Hex, 32字节):")
        self.private_key_lineedit = LineEdit()
        self.private_key_lineedit.setPlaceholderText("64个十六进制字符")
        self.private_key_lineedit.setMaxLength(64)
        self.private_key_lineedit.setReadOnly(True)
        self.load_private_key_button = PushButton(FIF.FOLDER, "加载", self)
        self.load_private_key_button.clicked.connect(self._load_private_key)
        self.save_private_key_button = PushButton(FIF.SAVE, "保存", self)
        self.save_private_key_button.clicked.connect(self._save_private_key)
        private_key_hlayout = QHBoxLayout()
        private_key_hlayout.addWidget(private_key_label)
        private_key_hlayout.addWidget(self.private_key_lineedit, 1)
        private_key_hlayout.addWidget(self.load_private_key_button)
        private_key_hlayout.addWidget(self.save_private_key_button)
        key_layout.addLayout(private_key_hlayout)
        
        public_key_label = BodyLabel("公钥 (Hex, 32字节):")
        self.public_key_lineedit = LineEdit()
        self.public_key_lineedit.setPlaceholderText("64个十六进制字符")
        self.public_key_lineedit.setMaxLength(64)
        self.public_key_lineedit.setReadOnly(True)
        self.load_public_key_button = PushButton(FIF.FOLDER, "加载", self)
        self.load_public_key_button.clicked.connect(self._load_public_key)
        self.save_public_key_button = PushButton(FIF.SAVE, "保存", self)
        self.save_public_key_button.clicked.connect(self._save_public_key)
        public_key_hlayout = QHBoxLayout()
        public_key_hlayout.addWidget(public_key_label)
        public_key_hlayout.addWidget(self.public_key_lineedit, 1)
        public_key_hlayout.addWidget(self.load_public_key_button)
        public_key_hlayout.addWidget(self.save_public_key_button)
        key_layout.addLayout(public_key_hlayout)
        
        self.key_group.setLayout(key_layout)
        self.main_vBoxLayout.addWidget(self.key_group)
    
    def _init_sign_ui(self):
        self.sign_group = QGroupBox("签名")
        sign_layout = QVBoxLayout()
        sign_layout.setSpacing(12)
        
        sign_title = StrongBodyLabel("文件签名")
        sign_layout.addWidget(sign_title)
        
        file_label = BodyLabel("待签名文件:")
        self.sign_file_lineedit = LineEdit()
        self.sign_file_lineedit.setPlaceholderText("选择要签名的文件")
        self.sign_file_lineedit.setReadOnly(True)
        self.sign_file_browse_button = PushButton(FIF.FOLDER, "浏览", self)
        self.sign_file_browse_button.clicked.connect(self._browse_sign_file)
        file_hlayout = QHBoxLayout()
        file_hlayout.addWidget(file_label)
        file_hlayout.addWidget(self.sign_file_lineedit, 1)
        file_hlayout.addWidget(self.sign_file_browse_button)
        sign_layout.addLayout(file_hlayout)
        
        output_label = BodyLabel("签名输出:")
        self.sign_output_lineedit = LineEdit()
        self.sign_output_lineedit.setPlaceholderText("签名文件路径（可选，默认为原文件.sig）")
        self.sign_output_browse_button = PushButton(FIF.SAVE, "浏览", self)
        self.sign_output_browse_button.clicked.connect(self._browse_sign_output)
        output_hlayout = QHBoxLayout()
        output_hlayout.addWidget(output_label)
        output_hlayout.addWidget(self.sign_output_lineedit, 1)
        output_hlayout.addWidget(self.sign_output_browse_button)
        sign_layout.addLayout(output_hlayout)
        
        self.sign_progress = ProgressBar()
        self.sign_progress.setValue(0)
        sign_layout.addWidget(self.sign_progress)
        
        self.sign_button = PushButton(FIF.FINGERPRINT, "执行签名", self)
        self.sign_button.clicked.connect(self._execute_sign)
        sign_layout.addWidget(self.sign_button)
        
        self.sign_group.setLayout(sign_layout)
        self.main_vBoxLayout.addWidget(self.sign_group)
    
    def _init_verify_ui(self):
        self.verify_group = QGroupBox("验证")
        verify_layout = QVBoxLayout()
        verify_layout.setSpacing(12)
        
        verify_title = StrongBodyLabel("签名验证")
        verify_layout.addWidget(verify_title)
        
        file_label = BodyLabel("待验证文件:")
        self.verify_file_lineedit = LineEdit()
        self.verify_file_lineedit.setPlaceholderText("选择要验证的文件")
        self.verify_file_lineedit.setReadOnly(True)
        self.verify_file_browse_button = PushButton(FIF.FOLDER, "浏览", self)
        self.verify_file_browse_button.clicked.connect(self._browse_verify_file)
        file_hlayout = QHBoxLayout()
        file_hlayout.addWidget(file_label)
        file_hlayout.addWidget(self.verify_file_lineedit, 1)
        file_hlayout.addWidget(self.verify_file_browse_button)
        verify_layout.addLayout(file_hlayout)
        
        sig_label = BodyLabel("签名文件:")
        self.sig_file_lineedit = LineEdit()
        self.sig_file_lineedit.setPlaceholderText("选择签名文件 (.sig)")
        self.sig_file_lineedit.setReadOnly(True)
        self.sig_file_browse_button = PushButton(FIF.FOLDER, "浏览", self)
        self.sig_file_browse_button.clicked.connect(self._browse_sig_file)
        sig_hlayout = QHBoxLayout()
        sig_hlayout.addWidget(sig_label)
        sig_hlayout.addWidget(self.sig_file_lineedit, 1)
        sig_hlayout.addWidget(self.sig_file_browse_button)
        verify_layout.addLayout(sig_hlayout)
        
        self.verify_progress = ProgressBar()
        self.verify_progress.setValue(0)
        verify_layout.addWidget(self.verify_progress)
        
        self.verify_button = PushButton(FIF.CHECKBOX, "验证签名", self)
        self.verify_button.clicked.connect(self._execute_verify)
        verify_layout.addWidget(self.verify_button)
        
        self.verify_group.setLayout(verify_layout)
        self.main_vBoxLayout.addWidget(self.verify_group)
        self.main_vBoxLayout.addStretch(1)
    
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
            getattr(self, 'key_group', None),
            getattr(self, 'sign_group', None),
            getattr(self, 'verify_group', None),
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
            self, "导出输出", "ed25519_output.txt", "文本文件 (*.txt);;所有文件 (*)"
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
    
    def _generate_key_pair(self):
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
        
        try:
            private_key = ECC.generate(curve='ed25519')
            self.private_key_pem = private_key.export_key(format='PEM')
            
            public_key = private_key.public_key()
            self.public_key_bytes = public_key.export_key(format='raw')
            
            private_hex = self._pem_to_hex(self.private_key_pem)
            self.private_key_lineedit.setText(private_hex)
            self.public_key_lineedit.setText(self.public_key_bytes.hex())
            
            self._log("Ed25519密钥对生成成功:")
            self._log(f"私钥: {private_hex}")
            self._log(f"公钥: {self.public_key_bytes.hex()}")
            
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
    
    def _load_private_key(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "加载私钥", "", "私钥文件 (*.key *.pem *.bin);;所有文件 (*)"
        )
        if file_path:
            try:
                with open(file_path, 'rb') as f:
                    data = f.read()
                
                if len(data) == 64:
                    self.private_key_pem = self._hex_to_pem(data.decode('utf-8').strip())
                elif len(data) == 32:
                    self.private_key_pem = self._raw_to_pem(data)
                else:
                    try:
                        pem_str = data.decode('utf-8')
                        if '-----BEGIN PRIVATE KEY-----' in pem_str:
                            self.private_key_pem = pem_str
                        else:
                            raise ValueError(f"无效的私钥格式")
                    except:
                        raise ValueError(f"无效的私钥长度: {len(data)} 字节")
                
                private_key = ECC.import_key(self.private_key_pem)
                public_key = private_key.public_key()
                self.public_key_bytes = public_key.export_key(format='raw')
                
                private_hex = self._pem_to_hex(self.private_key_pem)
                self.private_key_lineedit.setText(private_hex)
                self.public_key_lineedit.setText(self.public_key_bytes.hex())
                
                self._log(f"私钥加载成功: {file_path}")
                
                InfoBar.success(
                    title="加载成功",
                    content="私钥已加载",
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
    
    def _hex_to_pem(self, hex_str):
        raw_bytes = bytes.fromhex(hex_str)
        return self._raw_to_pem(raw_bytes)
    
    def _raw_to_pem(self, raw_bytes):
        header = b'\x30\x2e\x02\x01\x00\x30\x05\x06\x03\x2b\x65\x70\x04\x22\x04\x20'
        der_bytes = header + raw_bytes
        pem_content = base64.b64encode(der_bytes).decode('utf-8')
        pem_lines = [pem_content[i:i+64] for i in range(0, len(pem_content), 64)]
        return '-----BEGIN PRIVATE KEY-----\n' + '\n'.join(pem_lines) + '\n-----END PRIVATE KEY-----\n'
    
    def _save_private_key(self):
        if not self.private_key_pem:
            InfoBar.warning(
                title="警告",
                content="没有私钥可保存，请先生成或加载私钥",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存私钥", "ed25519_private.pem", "PEM文件 (*.pem);;二进制文件 (*.bin);;十六进制文件 (*.key);;所有文件 (*)"
        )
        if file_path:
            try:
                if file_path.endswith('.key'):
                    private_hex = self._pem_to_hex(self.private_key_pem)
                    with open(file_path, 'w') as f:
                        f.write(private_hex)
                elif file_path.endswith('.bin'):
                    pem_content = self.private_key_pem.replace('\n', '')
                    pem_content = pem_content.replace('-----BEGIN PRIVATE KEY-----', '')
                    pem_content = pem_content.replace('-----END PRIVATE KEY-----', '')
                    der_bytes = base64.b64decode(pem_content)
                    raw_bytes = der_bytes[16:48]
                    with open(file_path, 'wb') as f:
                        f.write(raw_bytes)
                else:
                    with open(file_path, 'w') as f:
                        f.write(self.private_key_pem)
                
                self._log(f"私钥已保存: {file_path}")
                InfoBar.success(
                    title="保存成功",
                    content=f"私钥已保存到 {file_path}",
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=3000,
                    parent=self,
                )
                
            except Exception as e:
                InfoBar.error(
                    title="保存失败",
                    content=str(e),
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=3000,
                    parent=self,
                )
    
    def _load_public_key(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "加载公钥", "", "公钥文件 (*.pub *.pem *.bin);;所有文件 (*)"
        )
        if file_path:
            try:
                with open(file_path, 'rb') as f:
                    data = f.read()
                
                if len(data) == 128:
                    self.public_key_bytes = bytes.fromhex(data.decode('utf-8').strip())
                elif len(data) == 32:
                    self.public_key_bytes = data
                else:
                    try:
                        public_key = ECC.import_key(data.decode('utf-8'))
                        self.public_key_bytes = public_key.export_key(format='raw')
                    except:
                        raise ValueError(f"无效的公钥长度: {len(data)} 字节")
                
                self.public_key_lineedit.setText(self.public_key_bytes.hex())
                self._log(f"公钥加载成功: {file_path}")
                
                InfoBar.success(
                    title="加载成功",
                    content="公钥已加载",
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=3000,
                    parent=self,
                )
                
            except Exception as e:
                self._log(f"公钥加载失败: {str(e)}")
                InfoBar.error(
                    title="加载失败",
                    content=str(e),
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=3000,
                    parent=self,
                )
    
    def _save_public_key(self):
        if not self.public_key_bytes:
            InfoBar.warning(
                title="警告",
                content="没有公钥可保存，请先生成或加载公钥",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存公钥", "ed25519_public.pub", "公钥文件 (*.pub);;所有文件 (*)"
        )
        if file_path:
            try:
                with open(file_path, 'wb') as f:
                    f.write(self.public_key_bytes)
                
                self._log(f"公钥已保存: {file_path}")
                InfoBar.success(
                    title="保存成功",
                    content=f"公钥已保存到 {file_path}",
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=3000,
                    parent=self,
                )
                
            except Exception as e:
                InfoBar.error(
                    title="保存失败",
                    content=str(e),
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=3000,
                    parent=self,
                )
    
    def _browse_sign_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择待签名文件", "", "所有文件 (*);;固件文件 (*.bin *.hex *.fw)"
        )
        if file_path:
            self.sign_file_lineedit.setText(file_path)
            self._log(f"待签名文件: {file_path}")
    
    def _browse_sign_output(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "选择签名输出路径", "", "签名文件 (*.sig);;所有文件 (*)"
        )
        if file_path:
            self.sign_output_lineedit.setText(file_path)
            self._log(f"签名输出路径: {file_path}")
    
    def _browse_verify_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择待验证文件", "", "所有文件 (*);;固件文件 (*.bin *.hex *.fw)"
        )
        if file_path:
            self.verify_file_lineedit.setText(file_path)
            self._log(f"待验证文件: {file_path}")
    
    def _browse_sig_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择签名文件", "", "签名文件 (*.sig);;所有文件 (*)"
        )
        if file_path:
            self.sig_file_lineedit.setText(file_path)
            self._log(f"签名文件: {file_path}")
    
    def _execute_sign(self):
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
        
        if not self.private_key_pem:
            InfoBar.warning(
                title="警告",
                content="请先生成或加载私钥",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return
        
        sign_file = self.sign_file_lineedit.text().strip()
        if not sign_file:
            InfoBar.warning(
                title="警告",
                content="请选择待签名文件",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return
        
        if not os.path.exists(sign_file):
            InfoBar.error(
                title="错误",
                content="待签名文件不存在",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return
        
        output_path = self.sign_output_lineedit.text().strip() or None
        
        self._log("开始签名...")
        self._log(f"文件: {sign_file}")
        
        self.sign_button.setEnabled(False)
        self.sign_progress.setValue(0)
        
        self.sign_thread = SignThread(sign_file, self.private_key_pem, output_path)
        self.sign_thread.progress_updated.connect(self._on_sign_progress)
        self.sign_thread.sign_completed.connect(self._on_sign_completed)
        self.sign_thread.error_occurred.connect(self._on_sign_error)
        self.sign_thread.start()
    
    def _on_sign_progress(self, value):
        self.sign_progress.setValue(value)
    
    def _on_sign_completed(self, success, message):
        self.sign_button.setEnabled(True)
        self._log(message)
        
        if success:
            InfoBar.success(
                title="签名成功",
                content="文件已成功签名",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
    
    def _on_sign_error(self, error):
        self.sign_button.setEnabled(True)
        self._log(f"错误: {error}")
        InfoBar.error(
            title="签名失败",
            content=error,
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=3000,
            parent=self,
        )
    
    def _execute_verify(self):
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
        
        if not self.public_key_bytes:
            InfoBar.warning(
                title="警告",
                content="请先生成或加载公钥",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return
        
        verify_file = self.verify_file_lineedit.text().strip()
        if not verify_file:
            InfoBar.warning(
                title="警告",
                content="请选择待验证文件",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return
        
        if not os.path.exists(verify_file):
            InfoBar.error(
                title="错误",
                content="待验证文件不存在",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return
        
        sig_file = self.sig_file_lineedit.text().strip()
        if not sig_file:
            InfoBar.warning(
                title="警告",
                content="请选择签名文件",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return
        
        if not os.path.exists(sig_file):
            InfoBar.error(
                title="错误",
                content="签名文件不存在",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return
        
        self._log("开始验证签名...")
        self._log(f"文件: {verify_file}")
        self._log(f"签名: {sig_file}")
        
        self.verify_button.setEnabled(False)
        self.verify_progress.setValue(0)
        
        self.verify_thread = VerifyThread(verify_file, sig_file, self.public_key_bytes)
        self.verify_thread.progress_updated.connect(self._on_verify_progress)
        self.verify_thread.verify_completed.connect(self._on_verify_completed)
        self.verify_thread.error_occurred.connect(self._on_verify_error)
        self.verify_thread.start()
    
    def _on_verify_progress(self, value):
        self.verify_progress.setValue(value)
    
    def _on_verify_completed(self, success, message):
        self.verify_button.setEnabled(True)
        self._log(message)
        
        if success:
            InfoBar.success(
                title="验证成功",
                content="签名验证通过",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
    
    def _on_verify_error(self, error):
        self.verify_button.setEnabled(True)
        self._log(f"错误: {error}")
        InfoBar.error(
            title="验证失败",
            content=error,
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=3000,
            parent=self,
        )


if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    w = Ed25519_Widget()
    w.show()
    sys.exit(app.exec())
