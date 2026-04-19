# coding:utf-8
import sys
import os
import subprocess
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
    ProgressBar,
    PlainTextEdit,
    isDarkTheme,
    SpinBox,
)
from settings.config import cfg

HPATCHLITE_TOOLS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)))
HDIFFI_EXE = os.path.join(HPATCHLITE_TOOLS_PATH, 'hdiffi.exe')
HPATCHI_EXE = os.path.join(HPATCHLITE_TOOLS_PATH, 'hpatchi.exe')


class DiffGenerateThread(QThread):
    progress_updated = pyqtSignal(int)
    diff_completed = pyqtSignal(bool, str)
    error_occurred = pyqtSignal(str)
    output_received = pyqtSignal(str)

    def __init__(self, old_file, new_file, diff_file, compress_type='tuz', compress_level='', dict_size=''):
        super().__init__()
        self.old_file = old_file
        self.new_file = new_file
        self.diff_file = diff_file
        self.compress_type = compress_type
        self.compress_level = compress_level
        self.dict_size = dict_size

    def run(self):
        try:
            self.progress_updated.emit(10)
            
            cmd = [HDIFFI_EXE]
            
            compress_arg = f"-c-{self.compress_type}"
            if self.compress_level:
                compress_arg += f"-{self.compress_level}"
            if self.dict_size and self.compress_type in ['tuz', 'tuzi', 'lzma', 'lzma2']:
                compress_arg += f"-{self.dict_size}"
            cmd.append(compress_arg)
            
            cmd.extend([self.old_file, self.new_file, self.diff_file])
            
            self.output_received.emit(f"执行命令: {' '.join(cmd)}")
            
            self.progress_updated.emit(30)
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )
            
            stdout, stderr = process.communicate()
            
            if stdout:
                self.output_received.emit(stdout)
            if stderr:
                self.output_received.emit(f"stderr: {stderr}")
            
            self.progress_updated.emit(90)
            
            if process.returncode != 0:
                self.error_occurred.emit(f"差分包制作失败，返回码: {process.returncode}\n{stderr}")
                return
            
            old_size = os.path.getsize(self.old_file)
            new_size = os.path.getsize(self.new_file)
            diff_size = os.path.getsize(self.diff_file)
            compression_ratio = (1 - diff_size / new_size) * 100 if new_size > 0 else 0
            
            self.progress_updated.emit(100)
            
            result_msg = (
                f"差分包制作成功！\n"
                f"旧文件大小: {old_size:,} 字节\n"
                f"新文件大小: {new_size:,} 字节\n"
                f"差分包大小: {diff_size:,} 字节\n"
                f"压缩率: {compression_ratio:.2f}%"
            )
            
            self.diff_completed.emit(True, result_msg)

        except Exception as e:
            self.error_occurred.emit(f"差分包制作失败: {str(e)}")


class DiffApplyThread(QThread):
    progress_updated = pyqtSignal(int)
    apply_completed = pyqtSignal(bool, str)
    error_occurred = pyqtSignal(str)
    output_received = pyqtSignal(str)

    def __init__(self, old_file, diff_file, new_file, cache_size='32k'):
        super().__init__()
        self.old_file = old_file
        self.diff_file = diff_file
        self.new_file = new_file
        self.cache_size = cache_size

    def run(self):
        try:
            self.progress_updated.emit(10)
            
            cmd = [HPATCHI_EXE, f"-s-{self.cache_size}", self.old_file, self.diff_file, self.new_file]
            
            self.output_received.emit(f"执行命令: {' '.join(cmd)}")
            
            self.progress_updated.emit(30)
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )
            
            stdout, stderr = process.communicate()
            
            if stdout:
                self.output_received.emit(stdout)
            if stderr:
                self.output_received.emit(f"stderr: {stderr}")
            
            self.progress_updated.emit(90)
            
            if process.returncode != 0:
                self.error_occurred.emit(f"差分升级失败，返回码: {process.returncode}\n{stderr}")
                return
            
            old_size = os.path.getsize(self.old_file)
            diff_size = os.path.getsize(self.diff_file)
            new_size = os.path.getsize(self.new_file)
            
            self.progress_updated.emit(100)
            
            result_msg = (
                f"差分升级成功！\n"
                f"旧文件大小: {old_size:,} 字节\n"
                f"差分包大小: {diff_size:,} 字节\n"
                f"新文件大小: {new_size:,} 字节\n"
                f"输出文件: {self.new_file}"
            )
            
            self.apply_completed.emit(True, result_msg)

        except Exception as e:
            self.error_occurred.emit(f"差分升级失败: {str(e)}")


class HPatchLite_Tools_Widget(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("hpatchlite_tools_widget")
        self.resize(1000, 700)
        
        self.Main_hLayout = QHBoxLayout(self)
        self.hpatchlite_setting_vBoxLayout = QVBoxLayout()
        self.hpatchlite_setting_vBoxLayout.setSpacing(10)
        self.hpatchlite_setting_vBoxLayout.setContentsMargins(30, 30, 30, 30)
        
        self._init_diff_generate_ui()
        self._init_diff_apply_ui()
        
        self.Main_hLayout.addLayout(self.hpatchlite_setting_vBoxLayout, 1)
        self._init_output_bar_ui()
        
        self.diff_generate_thread = None
        self.diff_apply_thread = None
        
        self.__updateTheme()
        cfg.themeChanged.connect(self.__updateTheme)

    def _init_diff_generate_ui(self):
        self.generate_group = QGroupBox("差分包制作 (hdiffi)")
        generate_layout = QVBoxLayout()
        generate_layout.setSpacing(12)
        
        title_label = StrongBodyLabel("生成差分包")
        generate_layout.addWidget(title_label)
        
        old_file_layout = QHBoxLayout()
        old_file_label = BodyLabel("旧版本文件:")
        self.old_file_edit = LineEdit()
        self.old_file_edit.setPlaceholderText("选择旧版本固件文件...")
        self.old_file_edit.setReadOnly(True)
        self.old_file_edit.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.old_file_btn = PushButton(FIF.FOLDER, "选择文件")
        self.old_file_btn.clicked.connect(self._select_old_file)
        old_file_layout.addWidget(old_file_label)
        old_file_layout.addWidget(self.old_file_edit)
        old_file_layout.addWidget(self.old_file_btn)
        generate_layout.addLayout(old_file_layout)
        
        new_file_layout = QHBoxLayout()
        new_file_label = BodyLabel("新版本文件:")
        self.new_file_edit = LineEdit()
        self.new_file_edit.setPlaceholderText("选择新版本固件文件...")
        self.new_file_edit.setReadOnly(True)
        self.new_file_edit.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.new_file_btn = PushButton(FIF.FOLDER, "选择文件")
        self.new_file_btn.clicked.connect(self._select_new_file)
        new_file_layout.addWidget(new_file_label)
        new_file_layout.addWidget(self.new_file_edit)
        new_file_layout.addWidget(self.new_file_btn)
        generate_layout.addLayout(new_file_layout)
        
        diff_file_layout = QHBoxLayout()
        diff_file_label = BodyLabel("差分包输出:")
        self.diff_file_edit = LineEdit()
        self.diff_file_edit.setPlaceholderText("选择差分包保存路径...")
        self.diff_file_edit.setReadOnly(True)
        self.diff_file_edit.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.diff_file_btn = PushButton(FIF.SAVE, "选择路径")
        self.diff_file_btn.clicked.connect(self._select_diff_file)
        diff_file_layout.addWidget(diff_file_label)
        diff_file_layout.addWidget(self.diff_file_edit)
        diff_file_layout.addWidget(self.diff_file_btn)
        generate_layout.addLayout(diff_file_layout)
        
        compress_layout = QHBoxLayout()
        compress_label = BodyLabel("压缩算法:")
        self.compress_combo = ComboBox()
        self.compress_combo.addItems(["tuz (tinyuz)", "tuzi", "zlib", "pzlib", "lzma", "lzma2"])
        self.compress_combo.setCurrentIndex(0)
        self.compress_combo.setFixedWidth(120)
        self.compress_combo.currentIndexChanged.connect(self._on_compress_changed)
        
        level_label = BodyLabel("压缩级别:")
        self.level_combo = ComboBox()
        self.level_combo.addItems(["默认", "1", "2", "3", "4", "5", "6", "7", "8", "9"])
        self.level_combo.setCurrentIndex(0)
        self.level_combo.setFixedWidth(80)
        
        dict_label = BodyLabel("字典大小:")
        self.dict_combo = ComboBox()
        self.dict_combo.addItems(["默认", "4k", "8k", "16k", "32k", "64k", "128k", "256k", "512k", "1m", "2m", "4m"])
        self.dict_combo.setCurrentIndex(0)
        self.dict_combo.setFixedWidth(80)
        
        compress_layout.addWidget(compress_label)
        compress_layout.addWidget(self.compress_combo)
        compress_layout.addSpacing(8)
        compress_layout.addWidget(level_label)
        compress_layout.addWidget(self.level_combo)
        compress_layout.addSpacing(8)
        compress_layout.addWidget(dict_label)
        compress_layout.addWidget(self.dict_combo)
        compress_layout.addStretch(1)
        generate_layout.addLayout(compress_layout)
        
        self.generate_progress = ProgressBar()
        self.generate_progress.setValue(0)
        generate_layout.addWidget(self.generate_progress)
        
        self.generate_btn = PushButton(FIF.DOWNLOAD, "生成差分包")
        self.generate_btn.clicked.connect(self._generate_diff)
        generate_layout.addWidget(self.generate_btn)
        
        self.generate_group.setLayout(generate_layout)
        self.hpatchlite_setting_vBoxLayout.addWidget(self.generate_group)

    def _init_diff_apply_ui(self):
        self.apply_group = QGroupBox("差分升级 (hpatchi)")
        apply_layout = QVBoxLayout()
        apply_layout.setSpacing(12)
        
        title_label = StrongBodyLabel("应用差分包")
        apply_layout.addWidget(title_label)
        
        old_file_layout = QHBoxLayout()
        old_file_label = BodyLabel("旧版本文件:")
        self.apply_old_file_edit = LineEdit()
        self.apply_old_file_edit.setPlaceholderText("选择旧版本固件文件...")
        self.apply_old_file_edit.setReadOnly(True)
        self.apply_old_file_edit.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.apply_old_file_btn = PushButton(FIF.FOLDER, "选择文件")
        self.apply_old_file_btn.clicked.connect(self._select_apply_old_file)
        old_file_layout.addWidget(old_file_label)
        old_file_layout.addWidget(self.apply_old_file_edit)
        old_file_layout.addWidget(self.apply_old_file_btn)
        apply_layout.addLayout(old_file_layout)
        
        diff_file_layout = QHBoxLayout()
        diff_file_label = BodyLabel("差分包文件:")
        self.apply_diff_file_edit = LineEdit()
        self.apply_diff_file_edit.setPlaceholderText("选择差分包文件...")
        self.apply_diff_file_edit.setReadOnly(True)
        self.apply_diff_file_edit.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.apply_diff_file_btn = PushButton(FIF.FOLDER, "选择文件")
        self.apply_diff_file_btn.clicked.connect(self._select_apply_diff_file)
        diff_file_layout.addWidget(diff_file_label)
        diff_file_layout.addWidget(self.apply_diff_file_edit)
        diff_file_layout.addWidget(self.apply_diff_file_btn)
        apply_layout.addLayout(diff_file_layout)
        
        new_file_layout = QHBoxLayout()
        new_file_label = BodyLabel("新文件输出:")
        self.apply_new_file_edit = LineEdit()
        self.apply_new_file_edit.setPlaceholderText("选择新文件保存路径...")
        self.apply_new_file_edit.setReadOnly(True)
        self.apply_new_file_edit.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.apply_new_file_btn = PushButton(FIF.SAVE, "选择路径")
        self.apply_new_file_btn.clicked.connect(self._select_apply_new_file)
        new_file_layout.addWidget(new_file_label)
        new_file_layout.addWidget(self.apply_new_file_edit)
        new_file_layout.addWidget(self.apply_new_file_btn)
        apply_layout.addLayout(new_file_layout)
        
        cache_layout = QHBoxLayout()
        cache_label = BodyLabel("缓存大小:")
        self.cache_combo = ComboBox()
        self.cache_combo.addItems(["3", "256", "1k", "8k", "16k", "32k", "64k", "128k", "256k", "512k", "1m", "2m", "4m"])
        self.cache_combo.setCurrentIndex(5)
        self.cache_combo.setFixedWidth(80)
        cache_layout.addWidget(cache_label)
        cache_layout.addWidget(self.cache_combo)
        cache_layout.addStretch(1)
        apply_layout.addLayout(cache_layout)
        
        self.apply_progress = ProgressBar()
        self.apply_progress.setValue(0)
        apply_layout.addWidget(self.apply_progress)
        
        self.apply_btn = PushButton(FIF.UPDATE, "应用差分包")
        self.apply_btn.clicked.connect(self._apply_diff)
        apply_layout.addWidget(self.apply_btn)
        
        self.apply_group.setLayout(apply_layout)
        self.hpatchlite_setting_vBoxLayout.addWidget(self.apply_group)

    def _init_output_bar_ui(self):
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
            getattr(self, 'generate_group', None),
            getattr(self, 'apply_group', None),
        ]
        
        for widget in widgets_to_update:
            if widget:
                widget.setStyleSheet(f"color: {text_color};")

    def _on_compress_changed(self, index):
        compress_type = self.compress_combo.currentText().split()[0]
        if compress_type in ['tuz', 'tuzi']:
            self.dict_combo.setEnabled(True)
            self.level_combo.setEnabled(False)
        elif compress_type in ['zlib', 'pzlib']:
            self.dict_combo.setEnabled(True)
            self.level_combo.setEnabled(True)
        elif compress_type in ['lzma', 'lzma2']:
            self.dict_combo.setEnabled(True)
            self.level_combo.setEnabled(True)
        else:
            self.dict_combo.setEnabled(False)
            self.level_combo.setEnabled(False)

    def _select_old_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择旧版本文件", "", "所有文件 (*);;固件文件 (*.bin *.hex *.fw)"
        )
        if file_path:
            self.old_file_edit.setText(file_path)
            self.log(f"已选择旧版本文件: {file_path}")

    def _select_new_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择新版本文件", "", "所有文件 (*);;固件文件 (*.bin *.hex *.fw)"
        )
        if file_path:
            self.new_file_edit.setText(file_path)
            self.log(f"已选择新版本文件: {file_path}")

    def _select_diff_file(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "选择差分包保存路径", "", "差分包文件 (*.diff *.patch *.hdiff);;所有文件 (*)"
        )
        if file_path:
            if not file_path.endswith(('.diff', '.patch', '.hdiff')):
                file_path += '.diff'
            self.diff_file_edit.setText(file_path)
            self.log(f"差分包将保存到: {file_path}")

    def _select_apply_old_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择旧版本文件", "", "所有文件 (*);;固件文件 (*.bin *.hex *.fw)"
        )
        if file_path:
            self.apply_old_file_edit.setText(file_path)
            self.log(f"已选择旧版本文件: {file_path}")

    def _select_apply_diff_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择差分包文件", "", "差分包文件 (*.diff *.patch *.hdiff);;所有文件 (*)"
        )
        if file_path:
            self.apply_diff_file_edit.setText(file_path)
            self.log(f"已选择差分包文件: {file_path}")

    def _select_apply_new_file(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "选择新文件保存路径", "", "所有文件 (*);;固件文件 (*.bin *.hex *.fw)"
        )
        if file_path:
            self.apply_new_file_edit.setText(file_path)
            self.log(f"新文件将保存到: {file_path}")

    def _generate_diff(self):
        old_file = self.old_file_edit.text().strip()
        new_file = self.new_file_edit.text().strip()
        diff_file = self.diff_file_edit.text().strip()

        if not old_file or not new_file or not diff_file:
            InfoBar.warning(
                title="警告",
                content="请选择所有必需的文件路径",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        if not os.path.exists(old_file):
            InfoBar.error(
                title="错误",
                content="旧版本文件不存在",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        if not os.path.exists(new_file):
            InfoBar.error(
                title="错误",
                content="新版本文件不存在",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        if not os.path.exists(HDIFFI_EXE):
            InfoBar.error(
                title="错误",
                content=f"hdiffi.exe 不存在: {HDIFFI_EXE}",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=5000,
                parent=self,
            )
            return

        compress_type = self.compress_combo.currentText().split()[0]
        level_text = self.level_combo.currentText()
        compress_level = '' if level_text == '默认' else level_text
        dict_text = self.dict_combo.currentText()
        dict_size = '' if dict_text == '默认' else dict_text

        self.generate_btn.setEnabled(False)
        self.generate_progress.setValue(0)
        self.log("开始生成差分包...")
        self.log(f"压缩算法: {compress_type}, 级别: {level_text}, 字典: {dict_text}")

        self.diff_generate_thread = DiffGenerateThread(
            old_file, new_file, diff_file, compress_type, compress_level, dict_size
        )
        self.diff_generate_thread.progress_updated.connect(self._on_generate_progress)
        self.diff_generate_thread.diff_completed.connect(self._on_generate_completed)
        self.diff_generate_thread.error_occurred.connect(self._on_error)
        self.diff_generate_thread.output_received.connect(self._on_output_received)
        self.diff_generate_thread.start()

    def _apply_diff(self):
        old_file = self.apply_old_file_edit.text().strip()
        diff_file = self.apply_diff_file_edit.text().strip()
        new_file = self.apply_new_file_edit.text().strip()

        if not old_file or not diff_file or not new_file:
            InfoBar.warning(
                title="警告",
                content="请选择所有必需的文件路径",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        if not os.path.exists(old_file):
            InfoBar.error(
                title="错误",
                content="旧版本文件不存在",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        if not os.path.exists(diff_file):
            InfoBar.error(
                title="错误",
                content="差分包文件不存在",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        if not os.path.exists(HPATCHI_EXE):
            InfoBar.error(
                title="错误",
                content=f"hpatchi.exe 不存在: {HPATCHI_EXE}",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=5000,
                parent=self,
            )
            return

        cache_size = self.cache_combo.currentText()

        self.apply_btn.setEnabled(False)
        self.apply_progress.setValue(0)
        self.log("开始应用差分包...")
        self.log(f"缓存大小: {cache_size}")

        self.diff_apply_thread = DiffApplyThread(old_file, diff_file, new_file, cache_size)
        self.diff_apply_thread.progress_updated.connect(self._on_apply_progress)
        self.diff_apply_thread.apply_completed.connect(self._on_apply_completed)
        self.diff_apply_thread.error_occurred.connect(self._on_error)
        self.diff_apply_thread.output_received.connect(self._on_output_received)
        self.diff_apply_thread.start()

    def _on_generate_progress(self, value):
        self.generate_progress.setValue(value)

    def _on_apply_progress(self, value):
        self.apply_progress.setValue(value)

    def _on_output_received(self, output):
        for line in output.strip().split('\n'):
            if line.strip():
                self.log(line.strip())

    def _on_generate_completed(self, success, message):
        self.generate_btn.setEnabled(True)
        self.log(message)
        if success:
            InfoBar.success(
                title="成功",
                content="差分包制作完成",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )

    def _on_apply_completed(self, success, message):
        self.apply_btn.setEnabled(True)
        self.log(message)
        if success:
            InfoBar.success(
                title="成功",
                content="差分升级完成",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )

    def _on_error(self, error_msg):
        self.generate_btn.setEnabled(True)
        self.apply_btn.setEnabled(True)
        self.log(f"错误: {error_msg}")
        InfoBar.error(
            title="错误",
            content=error_msg,
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=5000,
            parent=self,
        )

    def log(self, message):
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.output_area_text.appendPlainText(f"[{timestamp}] {message}")

    def clear_output(self):
        self.output_area_text.clear()

    def export_output(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出输出", "hpatchlite_output.txt", "文本文件 (*.txt);;所有文件 (*)"
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


if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    w = HPatchLite_Tools_Widget()
    w.show()
    sys.exit(app.exec())
