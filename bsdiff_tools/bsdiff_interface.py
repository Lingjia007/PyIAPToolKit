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
    LineEdit,
    ProgressBar,
    PlainTextEdit,
    isDarkTheme,
    CardWidget,
)
from settings.config import cfg

try:
    import bsdiff4
    BSDIFF_AVAILABLE = True
except ImportError:
    BSDIFF_AVAILABLE = False


class DiffGenerateThread(QThread):
    progress_updated = pyqtSignal(int)
    diff_completed = pyqtSignal(bool, str)
    error_occurred = pyqtSignal(str)

    def __init__(self, old_file, new_file, diff_file):
        super().__init__()
        self.old_file = old_file
        self.new_file = new_file
        self.diff_file = diff_file

    def run(self):
        if not BSDIFF_AVAILABLE:
            self.error_occurred.emit("bsdiff4库未安装，请使用 'pip install bsdiff4' 安装")
            return

        try:
            self.progress_updated.emit(10)
            
            old_size = os.path.getsize(self.old_file)
            new_size = os.path.getsize(self.new_file)
            
            self.progress_updated.emit(30)
            
            bsdiff4.file_diff(self.old_file, self.new_file, self.diff_file)
            
            self.progress_updated.emit(100)
            
            diff_size = os.path.getsize(self.diff_file)
            compression_ratio = (1 - diff_size / new_size) * 100 if new_size > 0 else 0
            
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

    def __init__(self, old_file, diff_file, new_file):
        super().__init__()
        self.old_file = old_file
        self.diff_file = diff_file
        self.new_file = new_file

    def run(self):
        if not BSDIFF_AVAILABLE:
            self.error_occurred.emit("bsdiff4库未安装，请使用 'pip install bsdiff4' 安装")
            return

        try:
            self.progress_updated.emit(10)
            
            old_size = os.path.getsize(self.old_file)
            diff_size = os.path.getsize(self.diff_file)
            
            self.progress_updated.emit(30)
            
            bsdiff4.file_patch(self.old_file, self.new_file, self.diff_file)
            
            self.progress_updated.emit(100)
            
            new_size = os.path.getsize(self.new_file)
            
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


class BSDiff_Tools_Widget(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("bsdiff_tools_widget")
        self.resize(1000, 700)
        
        self.Main_hLayout = QHBoxLayout(self)
        self.bsdiff_setting_vBoxLayout = QVBoxLayout()
        self.bsdiff_setting_vBoxLayout.setSpacing(10)
        self.bsdiff_setting_vBoxLayout.setContentsMargins(30, 30, 30, 30)
        
        self._init_diff_generate_ui()
        self._init_diff_apply_ui()
        
        self.Main_hLayout.addLayout(self.bsdiff_setting_vBoxLayout)
        self._init_output_bar_ui()
        
        self.diff_generate_thread = None
        self.diff_apply_thread = None
        
        self.__updateTheme()
        cfg.themeChanged.connect(self.__updateTheme)

    def _init_diff_generate_ui(self):
        self.generate_group = QGroupBox("差分包制作")
        generate_layout = QVBoxLayout()
        generate_layout.setSpacing(15)
        
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
        old_file_layout.addWidget(self.old_file_edit, 1)
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
        new_file_layout.addWidget(self.new_file_edit, 1)
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
        diff_file_layout.addWidget(self.diff_file_edit, 1)
        diff_file_layout.addWidget(self.diff_file_btn)
        generate_layout.addLayout(diff_file_layout)
        
        self.generate_progress = ProgressBar()
        self.generate_progress.setValue(0)
        generate_layout.addWidget(self.generate_progress)
        
        self.generate_btn = PushButton(FIF.DOWNLOAD, "生成差分包")
        self.generate_btn.clicked.connect(self._generate_diff)
        generate_layout.addWidget(self.generate_btn)
        
        self.generate_group.setLayout(generate_layout)
        self.bsdiff_setting_vBoxLayout.addWidget(self.generate_group)

    def _init_diff_apply_ui(self):
        self.apply_group = QGroupBox("差分升级")
        apply_layout = QVBoxLayout()
        apply_layout.setSpacing(15)
        
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
        old_file_layout.addWidget(self.apply_old_file_edit, 1)
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
        diff_file_layout.addWidget(self.apply_diff_file_edit, 1)
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
        new_file_layout.addWidget(self.apply_new_file_edit, 1)
        new_file_layout.addWidget(self.apply_new_file_btn)
        apply_layout.addLayout(new_file_layout)
        
        self.apply_progress = ProgressBar()
        self.apply_progress.setValue(0)
        apply_layout.addWidget(self.apply_progress)
        
        self.apply_btn = PushButton(FIF.UPDATE, "应用差分包")
        self.apply_btn.clicked.connect(self._apply_diff)
        apply_layout.addWidget(self.apply_btn)
        
        self.apply_group.setLayout(apply_layout)
        self.bsdiff_setting_vBoxLayout.addWidget(self.apply_group)

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
            self, "选择差分包保存路径", "", "差分包文件 (*.diff *.patch);;所有文件 (*)"
        )
        if file_path:
            if not file_path.endswith(('.diff', '.patch')):
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
            self, "选择差分包文件", "", "差分包文件 (*.diff *.patch);;所有文件 (*)"
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
        if not BSDIFF_AVAILABLE:
            InfoBar.error(
                title="错误",
                content="bsdiff4库未安装，请使用 'pip install bsdiff4' 安装",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=5000,
                parent=self,
            )
            return

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

        self.generate_btn.setEnabled(False)
        self.generate_progress.setValue(0)
        self.log("开始生成差分包...")

        self.diff_generate_thread = DiffGenerateThread(old_file, new_file, diff_file)
        self.diff_generate_thread.progress_updated.connect(self._on_generate_progress)
        self.diff_generate_thread.diff_completed.connect(self._on_generate_completed)
        self.diff_generate_thread.error_occurred.connect(self._on_error)
        self.diff_generate_thread.start()

    def _apply_diff(self):
        if not BSDIFF_AVAILABLE:
            InfoBar.error(
                title="错误",
                content="bsdiff4库未安装，请使用 'pip install bsdiff4' 安装",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=5000,
                parent=self,
            )
            return

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

        self.apply_btn.setEnabled(False)
        self.apply_progress.setValue(0)
        self.log("开始应用差分包...")

        self.diff_apply_thread = DiffApplyThread(old_file, diff_file, new_file)
        self.diff_apply_thread.progress_updated.connect(self._on_apply_progress)
        self.diff_apply_thread.apply_completed.connect(self._on_apply_completed)
        self.diff_apply_thread.error_occurred.connect(self._on_error)
        self.diff_apply_thread.start()

    def _on_generate_progress(self, value):
        self.generate_progress.setValue(value)

    def _on_apply_progress(self, value):
        self.apply_progress.setValue(value)

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
            self, "导出输出", "bsdiff_output.txt", "文本文件 (*.txt);;所有文件 (*)"
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
    w = BSDiff_Tools_Widget()
    w.show()
    sys.exit(app.exec())
