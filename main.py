# coding:utf-8
import sys
import os

from PyQt6.QtCore import Qt, QUrl, QLocale, QTranslator, QEventLoop, QTimer, QSize
from PyQt6.QtGui import QIcon, QDesktopServices
from PyQt6.QtWidgets import QApplication, QWidget, QHBoxLayout
from qfluentwidgets import (NavigationItemPosition, MessageBox, setTheme, Theme, FluentWindow,
                            NavigationAvatarWidget, SubtitleLabel, setFont, InfoBadge,
                            InfoBadgePosition, FluentTranslator, SplashScreen)
from qfluentwidgets import FluentIcon as FIF
from serial_tools.serial_interface import Serial_Tools_Widget, SerialTabWidget
from pyocd_tools.pyocd_interface import Pyocd_Tools_Widget
from aes_tools.aes_interface import AES_Tools_Widget
from bsdiff_tools.bsdiff_interface import BSDiff_Tools_Widget
from hpatchlite_tools.hpatchlite_interface import HPatchLite_Tools_Widget
from settings.setting_interface import SettingInterface
from settings.config import cfg, Language


class Widget(QWidget):

    def __init__(self, text: str, parent=None):
        super().__init__(parent=parent)
        self.label = SubtitleLabel(text, self)
        self.hBoxLayout = QHBoxLayout(self)

        setFont(self.label, 24)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hBoxLayout.addWidget(self.label, 1, Qt.AlignmentFlag.AlignCenter)
        self.setObjectName(text.replace(' ', '-'))


class Window(FluentWindow):

    def __init__(self):
        super().__init__()

        self.homeInterface = Widget('Home Interface', self)
        self.serialInterface = SerialTabWidget()
        self.pyocdInterface = Pyocd_Tools_Widget()
        self.aesInterface = AES_Tools_Widget()
        self.bsdiffInterface = BSDiff_Tools_Widget()
        self.hpatchliteInterface = HPatchLite_Tools_Widget()
        self.settingInterface = SettingInterface(self)

        self.initNavigation()
        self.initWindow()

        self.splashScreen = SplashScreen(self.windowIcon(), self)
        self.splashScreen.setIconSize(QSize(102, 102))

        self.show()
        self.createSubInterface()
        self.splashScreen.finish()

        # 连接 CM pack 路径变化信号
        self.settingInterface.cmPackPathChanged.connect(self.pyocdInterface.scan_targets)

        self.switchTo(self.serialInterface)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        print(f"Main Window Size: {self.width()} x {self.height()}")

    def createSubInterface(self):
        loop = QEventLoop(self)
        QTimer.singleShot(1000, loop.quit)
        loop.exec()

    def initNavigation(self):
        self.addSubInterface(self.serialInterface, FIF.DEVELOPER_TOOLS, 'Serial Port')
        self.addSubInterface(self.pyocdInterface, FIF.DOWNLOAD, 'PyOCD烧录')    
        self.addSubInterface(self.aesInterface, FIF.FINGERPRINT, 'AES加密')
        self.addSubInterface(self.bsdiffInterface, FIF.UPDATE, '差分升级')
        self.addSubInterface(self.hpatchliteInterface, FIF.ZIP_FOLDER, 'HPatchLite')
        self.addSubInterface(self.homeInterface, FIF.HOME, 'Home')

        self.navigationInterface.addWidget(
            routeKey='avatar',
            widget=NavigationAvatarWidget('Lingsir007', 'settings/resource/images/lingsir007.png'),
            onClick=self.showMessageBox,
            position=NavigationItemPosition.BOTTOM,
        )

        self.addSubInterface(self.settingInterface, FIF.SETTING, 'Settings', NavigationItemPosition.BOTTOM)

    def showMessageBox(self):
        w = MessageBox(
            '支持作者🥰',
            '个人开发不易，如果这个项目帮助到了您，可以考虑请作者喝一瓶快乐水🥤。您的支持就是作者开发和维护项目的动力🚀。',
            self
        )
        w.yesButton.setText('确定')
        w.cancelButton.setText('取消')

        if w.exec():
            QDesktopServices.openUrl(QUrl("https://github.com/Lingjia007"))

    def initWindow(self):
        self.resize(1055, 745)
        self.setWindowIcon(QIcon('settings/resource/images/logo.png'))
        self.setWindowTitle('IAP Host Computer')

        from PyQt6.QtGui import QGuiApplication
        screen = QGuiApplication.primaryScreen()
        if screen:
            desktop = screen.availableGeometry()
            w, h = desktop.width(), desktop.height()
            self.move(w//2 - self.width()//2, h//2 - self.height()//2)


if __name__ == '__main__':
    if cfg.get(cfg.dpiScale) == "Auto":
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    else:
        os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
        os.environ["QT_SCALE_FACTOR"] = str(cfg.get(cfg.dpiScale))

    app = QApplication(sys.argv)

    locale = cfg.get(cfg.language).value
    fluentTranslator = FluentTranslator(locale)
    settingTranslator = QTranslator()
    settings_i18n_path = os.path.join(os.path.dirname(__file__), 'settings', 'resource', 'i18n')
    settingTranslator.load(locale, "settings", ".", settings_i18n_path)

    app.installTranslator(fluentTranslator)
    app.installTranslator(settingTranslator)

    w = Window()
    app.exec()
