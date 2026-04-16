# coding:utf-8
import os
from enum import Enum

from PyQt6.QtCore import Qt, QLocale
from PyQt6.QtGui import QGuiApplication, QFont
from qfluentwidgets import (qconfig, QConfig, ConfigItem, OptionsConfigItem, BoolValidator,
                            ColorConfigItem, OptionsValidator, RangeConfigItem, RangeValidator,
                            FolderListValidator, EnumSerializer, FolderValidator, ConfigSerializer, __version__)


class BaudRate(Enum):
    """ Serial baud rate enumeration """
    BAUD_9600 = 9600
    BAUD_19200 = 19200
    BAUD_38400 = 38400
    BAUD_57600 = 57600
    BAUD_115200 = 115200


class DataBits(Enum):
    """ Serial data bits enumeration """
    DATA_5 = 5
    DATA_6 = 6
    DATA_7 = 7
    DATA_8 = 8


class StopBits(Enum):
    """ Serial stop bits enumeration """
    ONE = 1
    ONE_POINT_FIVE = 1.5
    TWO = 2


class Parity(Enum):
    """ Serial parity enumeration """
    NONE = "None"
    EVEN = "Even"
    ODD = "Odd"


class SongQuality(Enum):
    """ Online song quality enumeration class """

    STANDARD = "Standard quality"
    HIGH = "High quality"
    SUPER = "Super quality"
    LOSSLESS = "Lossless quality"


class MvQuality(Enum):
    """ MV quality enumeration class """

    FULL_HD = "Full HD"
    HD = "HD"
    SD = "SD"
    LD = "LD"


class Language(Enum):
    """ Language enumeration """

    CHINESE_SIMPLIFIED = QLocale(QLocale.Language.Chinese, QLocale.Country.China)
    CHINESE_TRADITIONAL = QLocale(QLocale.Language.Chinese, QLocale.Country.HongKong)
    ENGLISH = QLocale(QLocale.Language.English)
    AUTO = QLocale()


class LanguageSerializer(ConfigSerializer):
    """ Language serializer """

    def serialize(self, language):
        return language.value.name() if language != Language.AUTO else "Auto"

    def deserialize(self, value: str):
        return Language(QLocale(value)) if value != "Auto" else Language.AUTO


class Config(QConfig):
    """ Config of application """

    # folders
    musicFolders = ConfigItem(
        "Folders", "LocalMusic", [], FolderListValidator())
    downloadFolder = ConfigItem(
        "Folders", "Download", "download", FolderValidator())

    # online
    onlineSongQuality = OptionsConfigItem(
        "Online", "SongQuality", SongQuality.STANDARD, OptionsValidator(SongQuality), EnumSerializer(SongQuality))
    onlinePageSize = RangeConfigItem(
        "Online", "PageSize", 30, RangeValidator(0, 50))
    onlineMvQuality = OptionsConfigItem(
        "Online", "MvQuality", MvQuality.FULL_HD, OptionsValidator(MvQuality), EnumSerializer(MvQuality))

    # main window
    enableAcrylicBackground = ConfigItem(
        "MainWindow", "EnableAcrylicBackground", False, BoolValidator())
    minimizeToTray = ConfigItem(
        "MainWindow", "MinimizeToTray", True, BoolValidator())
    playBarColor = ColorConfigItem("MainWindow", "PlayBarColor", "#225C7F")
    recentPlaysNumber = RangeConfigItem(
        "MainWindow", "RecentPlayNumbers", 300, RangeValidator(10, 300))
    dpiScale = OptionsConfigItem(
        "MainWindow", "DpiScale", "Auto", OptionsValidator([1, 1.25, 1.5, 1.75, 2, "Auto"]), restart=True)
    language = OptionsConfigItem(
        "MainWindow", "Language", Language.AUTO, OptionsValidator(Language), LanguageSerializer(), restart=True)

    # desktop lyric
    deskLyricHighlightColor = ColorConfigItem(
        "DesktopLyric", "HighlightColor", "#0099BC")
    deskLyricFontSize = RangeConfigItem(
        "DesktopLyric", "FontSize", 50, RangeValidator(15, 50))
    deskLyricStrokeSize = RangeConfigItem(
        "DesktopLyric", "StrokeSize", 5, RangeValidator(0, 20))
    deskLyricStrokeColor = ColorConfigItem(
        "DesktopLyric", "StrokeColor", Qt.GlobalColor.black)
    deskLyricFontFamily = ConfigItem(
        "DesktopLyric", "FontFamily", "Microsoft YaHei")
    deskLyricAlignment = OptionsConfigItem(
        "DesktopLyric", "Alignment", "Center", OptionsValidator(["Center", "Left", "Right"]))

    # software update
    checkUpdateAtStartUp = ConfigItem(
        "Update", "CheckUpdateAtStartUp", True, BoolValidator())

    # serial port settings
    serialFontSize = RangeConfigItem(
        "SerialPort", "FontSize", 10, RangeValidator(4, 100))
    serialFontFamily = ConfigItem(
        "SerialPort", "FontFamily", "Consolas")
    serialDtrState = ConfigItem(
        "SerialPort", "DtrState", False, BoolValidator())
    serialRtsState = ConfigItem(
        "SerialPort", "RtsState", False, BoolValidator())
    serialSendFontSize = RangeConfigItem(
        "SerialPort", "SendFontSize", 10, RangeValidator(4, 100))
    
    # pyocd settings
    pyocdFirmwarePath = ConfigItem(
        "PyOCD", "FirmwarePath", "")
    pyocdTrustCrc = ConfigItem(
        "PyOCD", "TrustCrc", True, BoolValidator())

    # CM pack settings
    cmPackPath = ConfigItem(
        "CMPack", "PackPath", "C:\\Users\\31254\\AppData\\Local\\cmsis-pack-manager\\cmsis-pack-manager\\Keil\\STM32F4xx_DFP", FolderValidator())

    @property
    def serialFont(self):
        """ get the serial port font """
        font = QFont(self.serialFontFamily.value)
        font.setPointSize(self.serialFontSize.value)
        font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias | QFont.StyleStrategy.PreferQuality)
        return font

    @serialFont.setter
    def serialFont(self, font: QFont):
        self.serialFontFamily.value = font.family()
        self.serialFontSize.value = font.pointSize()
        self.save()

    @property
    def desktopLyricFont(self):
        """ get the desktop lyric font """
        font = QFont(self.deskLyricFontFamily.value)
        font.setPixelSize(self.deskLyricFontSize.value)
        dpi = QGuiApplication.primaryScreen().logicalDotsPerInch()
        point_size = max(1, int(self.deskLyricFontSize.value * 72 / dpi))
        font.setPointSize(point_size)
        return font

    @desktopLyricFont.setter
    def desktopLyricFont(self, font: QFont):
        dpi = QGuiApplication.primaryScreen().logicalDotsPerInch()
        self.deskLyricFontFamily.value = font.family()
        point_size = font.pointSize()
        if point_size > 0:
            self.deskLyricFontSize.value = max(15, int(point_size * dpi / 72))
        else:
            pixel_size = font.pixelSize()
            if pixel_size > 0:
                self.deskLyricFontSize.value = max(15, pixel_size)
            else:
                self.deskLyricFontSize.value = 50
        self.save()


YEAR = 2023
AUTHOR = "zhiyiYo"
VERSION = __version__
HELP_URL = "https://pyqt-fluent-widgets.readthedocs.io"
FEEDBACK_URL = "https://github.com/zhiyiYo/PyQt-Fluent-Widgets/issues"
RELEASE_URL = "https://github.com/zhiyiYo/PyQt-Fluent-Widgets/releases/latest"


cfg = Config()
qconfig.load('settings/config/config.json', cfg)