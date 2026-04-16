# coding:utf-8
import sys
import os
import re
import subprocess
import zipfile
import xml.etree.ElementTree as ET
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QStackedWidget,
    QLabel,
    QFileDialog,
    QGroupBox,
)

from qfluentwidgets import (
    FluentIcon as FIF,
    SegmentedWidget,
    InfoBar,
    InfoBarPosition,
    BodyLabel,
    StrongBodyLabel,
    PushButton,
    ComboBox,
    LineEdit,
    CheckBox,
    SpinBox,
    ProgressRing,
    ProgressBar,
    PlainTextEdit,
    TextEdit,
    isDarkTheme,
)
from settings.config import cfg

try:
    from pyocd.core.helpers import ConnectHelper
    from pyocd.flash.file_programmer import FileProgrammer
    from pyocd.core.target import Target
    from pyocd.core.session import Session
    PYOCD_AVAILABLE = True
except ImportError:
    PYOCD_AVAILABLE = False


class Pyocd_List_Probes_Thread(QThread):
    probes_found = pyqtSignal(list)
    error_occurred = pyqtSignal(str)

    def __init__(self):
        super().__init__()

    def run(self):
        if not PYOCD_AVAILABLE:
            self.error_occurred.emit("pyocd库未安装，请使用 'pip install pyocd' 安装")
            return

        try:
            probes = ConnectHelper.get_all_connected_probes()
            
            probe_list = []
            for i, probe in enumerate(probes):
                probe_info = {
                    'index': str(i),
                    'name': probe.product_name if hasattr(probe, 'product_name') else str(probe.description),
                    'unique_id': probe.unique_id if hasattr(probe, 'unique_id') else str(id(probe)),
                    'display': f"{i}: {probe.product_name if hasattr(probe, 'product_name') else str(probe.description)} ({probe.unique_id if hasattr(probe, 'unique_id') else 'N/A'})"
                }
                probe_list.append(probe_info)
            
            self.probes_found.emit(probe_list)
        except Exception as e:
            self.error_occurred.emit(str(e))


class Pyocd_List_Targets_Thread(QThread):
    targets_found = pyqtSignal(list)
    error_occurred = pyqtSignal(str)

    def __init__(self):
        super().__init__()

    def run(self):
        target_list = []
        
        # 扫描 CMSIS pack 目录获取 target 列表
        try:
            # 使用设置中的 CM pack 路径的父目录（包含所有 pack 的目录）
            pack_path = cfg.get(cfg.cmPackPath)
            if pack_path:
                # 获取 pack 路径的父目录
                parent_dir = os.path.dirname(pack_path)
                if not parent_dir or not os.path.exists(parent_dir):
                    parent_dir = pack_path
                
                # 扫描父目录下的所有 pack 文件
                for root, dirs, files in os.walk(parent_dir):
                    for file in files:
                        if file.endswith('.pack'):
                            # 解析 pack 文件获取 target 信息
                            pack_file = os.path.join(root, file)
                            targets = self._parse_pack_targets(pack_file)
                            for target in targets:
                                if target and target not in target_list:
                                    target_list.append(target)
                
                target_list.sort()
                
                if len(target_list) > 0:
                    self.targets_found.emit(target_list)
                    return
        except Exception as e:
            self.error_occurred.emit(str(e))
            pass
        
        # 如果扫描 pack 目录失败，尝试使用 pyOCD API
        if PYOCD_AVAILABLE:
            try:
                from pyocd.target import TARGET
                
                # 获取所有内置 target
                for target_name in TARGET.keys():
                    if target_name and target_name not in target_list:
                        target_list.append(target_name)
                
                target_list.sort()
                
                if len(target_list) > 0:
                    self.targets_found.emit(target_list)
                    return
            except:
                pass
            
            # 尝试其他 API
            try:
                from pyocd.core.soc_target import SoCTarget
                known_targets = SoCTarget.get_known_targets()
                for target in known_targets:
                    if hasattr(target, 'name') and target.name:
                        if target.name not in target_list:
                            target_list.append(target.name)
                    elif hasattr(target, 'part_number') and target.part_number:
                        if target.part_number not in target_list:
                            target_list.append(target.part_number)
                
                target_list.sort()
                
                if len(target_list) > 0:
                    self.targets_found.emit(target_list)
                    return
            except:
                pass
        
        # 如果都失败，使用默认列表
        if len(target_list) == 0:
            target_list.extend([
                "stm32f407vg",
                "stm32f407zg", 
                "stm32f411re",
                "stm32f103c8",
                "stm32f103rb",
                "stm32f401re",
                "stm32f429zi",
                "stm32l476rg",
                "nrf52840",
                "lpc1768",
            ])
        
        self.targets_found.emit(target_list)
    
    def _parse_pack_targets(self, pack_file):
        """ 解析 pack 文件获取 target 信息 """
        targets = []
        try:
            with zipfile.ZipFile(pack_file, 'r') as z:
                pdsc_files = [n for n in z.namelist() if n.endswith('.pdsc')]
                if not pdsc_files:
                    return targets
                content = z.read(pdsc_files[0]).decode('utf-8')
                root = ET.fromstring(content)
                
                for device in root.findall('.//device'):
                    dname = device.get('Dname')
                    if dname and dname not in targets:
                        targets.append(dname.lower())
                    for variant in device.findall('.//variant'):
                        dvariant = variant.get('Dvariant')
                        if dvariant and dvariant not in targets:
                            targets.append(dvariant.lower())
        except:
            pass
        return targets


class Pyocd_Program_Thread(QThread):
    output_received = pyqtSignal(str)
    error_received = pyqtSignal(str)
    finished = pyqtSignal(int)
    progress_updated = pyqtSignal(int, int)

    def __init__(self, file_path, target=None, probe_uid=None, frequency=None, 
                 connect_mode=None, erase_mode=None, base_address=None, 
                 trust_crc=False, no_reset=False, pre_reset=False, config=None, pack=None):
        super().__init__()
        self.file_path = file_path
        self.target = target
        self.probe_uid = probe_uid
        self.frequency = frequency
        self.connect_mode = connect_mode
        self.erase_mode = erase_mode
        self.base_address = base_address
        self.trust_crc = trust_crc
        self.no_reset = no_reset
        self.pre_reset = pre_reset
        self.config = config
        self.pack = pack

    def run(self):
        if not PYOCD_AVAILABLE:
            self.error_received.emit("pyocd库未安装，请使用 'pip install pyocd' 安装")
            self.finished.emit(1)
            return

        try:
            self.output_received.emit(f"正在连接目标设备...")
            
            pack_path = cfg.get(cfg.cmPackPath)
            if pack_path:
                parent_dir = os.path.dirname(pack_path)
                if parent_dir and os.path.exists(parent_dir):
                    os.environ["CMSIS_PACK_ROOT"] = parent_dir
            
            connect_mode_map = {
                'halt': 'halt',
                'pre-reset': 'pre-reset',
                'under-reset': 'under-reset',
                'attach': 'attach'
            }
            
            connect_kwargs = {}
            if self.target:
                connect_kwargs['target_override'] = self.target
            
            if self.probe_uid:
                connect_kwargs['unique_id'] = self.probe_uid
            
            if self.frequency:
                freq_str = self.frequency.upper().replace('M', '000000').replace('K', '000')
                try:
                    connect_kwargs['frequency'] = int(freq_str)
                except ValueError:
                    pass
            
            if self.connect_mode:
                connect_kwargs['connect_mode'] = connect_mode_map.get(self.connect_mode, 'halt')
            
            if self.pre_reset:
                self.output_received.emit("正在执行烧录前复位...")
                try:
                    temp_session = ConnectHelper.session_with_chosen_probe(**connect_kwargs)
                    if temp_session:
                        with temp_session:
                            temp_target = temp_session.target
                            temp_target.reset()
                            self.output_received.emit("烧录前复位完成")
                except Exception as e:
                    self.output_received.emit(f"烧录前复位警告: {str(e)}")
            
            session = ConnectHelper.session_with_chosen_probe(**connect_kwargs)
            
            if session is None:
                self.error_received.emit("无法连接到调试器")
                self.finished.emit(1)
                return
            
            with session:
                board = session.board
                target = session.target
                
                self.output_received.emit(f"已连接: {board.name if board else 'Unknown'}")
                self.output_received.emit(f"目标芯片: {target.part_number if hasattr(target, 'part_number') else 'Unknown'}")
                
                def progress_callback(progress):
                    try:
                        percentage = int(progress * 100)
                        self.progress_updated.emit(percentage, 100)
                    except:
                        pass
                
                programmer = FileProgrammer(session, progress=progress_callback)
                
                erase_mode_map = {
                    'auto': 'auto',
                    'chip': 'chip',
                    'sector': 'sector'
                }
                
                program_kwargs = {}
                if self.erase_mode:
                    program_kwargs['erase'] = erase_mode_map.get(self.erase_mode, 'sector')
                
                if self.base_address:
                    try:
                        program_kwargs['base_address'] = int(self.base_address, 0)
                    except ValueError:
                        self.error_received.emit(f"无效的基地址: {self.base_address}")
                        self.finished.emit(1)
                        return
                
                if self.trust_crc:
                    program_kwargs['trust_crc'] = True
                
                self.output_received.emit(f"正在烧录固件: {self.file_path}")
                
                programmer.program(self.file_path, progress_cb=progress_callback, **program_kwargs)
                
                self.output_received.emit("固件烧录完成")
                
                if not self.no_reset:
                    self.output_received.emit("正在复位目标设备...")
                    target.reset()
                    self.output_received.emit("目标设备已复位")
                
                self.finished.emit(0)
                
        except Exception as e:
            self.error_received.emit(f"烧录失败: {str(e)}")
            self.finished.emit(1)


class Pyocd_Tools_Widget(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("pyocd_setting_widget")
        self.resize(1000, 700)
        self.pivot = SegmentedWidget(self)
        self.stackedWidget = QStackedWidget(self)
        self.Main_hLayout = QHBoxLayout(self)
        self.pyocd_setting_vBoxLayout = QVBoxLayout()
        self.pyocd_setting = QWidget()
        self.more_setting = QWidget()
        self.add_sub_interface(self.pyocd_setting, "pyocd_setting", "烧录设置")
        self.add_sub_interface(self.more_setting, "more_setting", "更多设置")

        self.pyocd_setting_vBoxLayout.addWidget(self.pivot)
        self.pyocd_setting_vBoxLayout.addWidget(self.stackedWidget)
        self.pyocd_setting_vBoxLayout.addStretch(1)
        self.Main_hLayout.addLayout(self.pyocd_setting_vBoxLayout)
        self.init_output_bar_ui()
        self.stackedWidget.setCurrentWidget(self.pyocd_setting)
        self.pivot.setCurrentItem("pyocd_setting")
        self.pivot.currentItemChanged.connect(self._on_pivot_changed)
        self.init_pyocd_setting_ui()
        self.init_more_setting_ui()

        self.current_command = ""
        self.program_thread = None
        self.list_probes_thread = None
        self.list_targets_thread = None
        self.probes_data = []
        self.targets_data = []
        self.last_probes_data = []  # 保存上次的调试器数据，用于比较变化
        
        # 后台自动检查调试器
        self.probe_timer = QTimer(self)
        self.probe_timer.timeout.connect(self.scan_probes)
        self.probe_timer.start(5000)  # 每5秒检查一次
        
        # 从配置加载设置
        self.file_path_lineedit.setText(cfg.pyocdFirmwarePath.value)
        self.trust_crc_checkbox.setChecked(cfg.pyocdTrustCrc.value)
        
        # 主题处理
        self.__updateTheme()
        cfg.themeChanged.connect(self.__updateTheme)

    def add_sub_interface(self, widget, object_name, text):
        widget.setObjectName(object_name)
        self.stackedWidget.addWidget(widget)
        self.pivot.addItem(
            routeKey=object_name,
            text=text,
            onClick=lambda: self.stackedWidget.setCurrentWidget(widget)
        )

    def _on_pivot_changed(self, key):
        self.stackedWidget.setCurrentWidget(self.findChild(QWidget, key))

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

    def init_pyocd_setting_ui(self):
        main_pyocd_setting_layout = QVBoxLayout()

        self.file_group = QGroupBox("固件文件")
        file_layout = QVBoxLayout()
        self.file_path_lineedit = LineEdit()
        self.file_path_lineedit.setPlaceholderText("请选择固件文件路径")
        self.browse_file_button = PushButton(FIF.FOLDER, "浏览", self)
        self.browse_file_button.clicked.connect(self.browse_file)
        file_path_layout = QHBoxLayout()
        file_path_layout.addWidget(self.file_path_lineedit, 1)
        file_path_layout.addWidget(self.browse_file_button)
        file_layout.addLayout(file_path_layout)
        self.file_group.setLayout(file_layout)
        main_pyocd_setting_layout.addWidget(self.file_group)

        self.target_group = QGroupBox("目标设置")
        target_layout = QVBoxLayout()

        self.target_label = BodyLabel("目标类型:")
        self.target_combo = ComboBox()
        self.target_combo.setPlaceholderText("请选择目标类型")
        self.target_combo.setFixedWidth(120)
        target_hlayout = QHBoxLayout()
        target_hlayout.addWidget(self.target_label)
        target_hlayout.addStretch(1)
        target_hlayout.addWidget(self.target_combo)
        target_hlayout.setContentsMargins(0, 2, 0, 2)
        target_layout.addLayout(target_hlayout)

        probe_label = BodyLabel("调试器:")
        self.probe_combo = ComboBox()
        self.probe_combo.setPlaceholderText("请选择调试器")
        self.probe_combo.setFixedWidth(120)
        probe_hlayout = QHBoxLayout()
        probe_hlayout.addWidget(probe_label)
        probe_hlayout.addStretch(1)
        probe_hlayout.addWidget(self.probe_combo)
        probe_hlayout.setContentsMargins(0, 2, 0, 2)
        target_layout.addLayout(probe_hlayout)

        frequency_label = BodyLabel("SWD频率:")
        self.frequency_combo = ComboBox()
        self.frequency_combo.addItems(["1M", "2M", "4M", "8M", "10M", "16M", "20M", "50M"])
        self.frequency_combo.setCurrentIndex(6)
        self.frequency_combo.setFixedWidth(120)
        frequency_hlayout = QHBoxLayout()
        frequency_hlayout.addWidget(frequency_label)
        frequency_hlayout.addStretch(1)
        frequency_hlayout.addWidget(self.frequency_combo)
        frequency_hlayout.setContentsMargins(0, 2, 0, 2)
        target_layout.addLayout(frequency_hlayout)

        connect_mode_label = BodyLabel("连接模式:")
        self.connect_mode_combo = ComboBox()
        self.connect_mode_combo.addItems(["halt", "pre-reset", "under-reset", "attach"])
        self.connect_mode_combo.setCurrentIndex(2)
        self.connect_mode_combo.setFixedWidth(120)
        connect_mode_hlayout = QHBoxLayout()
        connect_mode_hlayout.addWidget(connect_mode_label)
        connect_mode_hlayout.addStretch(1)
        connect_mode_hlayout.addWidget(self.connect_mode_combo)
        connect_mode_hlayout.setContentsMargins(0, 2, 0, 2)
        target_layout.addLayout(connect_mode_hlayout)

        self.target_group.setLayout(target_layout)
        main_pyocd_setting_layout.addWidget(self.target_group)

        self.load_group = QGroupBox("烧录选项")
        load_layout = QVBoxLayout()

        erase_label = BodyLabel("擦除方式:")
        self.erase_combo = ComboBox()
        self.erase_combo.addItems(["auto", "chip", "sector"])
        self.erase_combo.setCurrentIndex(2)
        self.erase_combo.setFixedWidth(120)
        erase_hlayout = QHBoxLayout()
        erase_hlayout.addWidget(erase_label)
        erase_hlayout.addStretch(1)
        erase_hlayout.addWidget(self.erase_combo)
        erase_hlayout.setContentsMargins(0, 2, 0, 2)
        load_layout.addLayout(erase_hlayout)

        address_label = BodyLabel("基地址:")
        self.address_lineedit = LineEdit()
        self.address_lineedit.setPlaceholderText("留空使用默认地址")
        self.address_lineedit.setFixedWidth(120)
        address_hlayout = QHBoxLayout()
        address_hlayout.addWidget(address_label)
        address_hlayout.addStretch(1)
        address_hlayout.addWidget(self.address_lineedit)
        address_hlayout.setContentsMargins(0, 2, 0, 2)
        load_layout.addLayout(address_hlayout)

        self.trust_crc_checkbox = CheckBox("使用CRC检查")
        self.trust_crc_checkbox.stateChanged.connect(self.__onTrustCrcChanged)
        load_layout.addWidget(self.trust_crc_checkbox)

        self.pre_reset_checkbox = CheckBox("烧录前复位")
        self.pre_reset_checkbox.setChecked(True)
        load_layout.addWidget(self.pre_reset_checkbox)

        self.no_reset_checkbox = CheckBox("烧录后不复位")
        load_layout.addWidget(self.no_reset_checkbox)

        self.load_group.setLayout(load_layout)
        main_pyocd_setting_layout.addWidget(self.load_group)

        self.progress_group = QGroupBox("烧录进度")
        progress_layout = QVBoxLayout()
        
        self.progress_bar = ProgressBar(self)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(8)
        progress_layout.addWidget(self.progress_bar)
        
        self.progress_label = BodyLabel("准备就绪")
        progress_layout.addWidget(self.progress_label)
        
        self.progress_group.setLayout(progress_layout)
        main_pyocd_setting_layout.addWidget(self.progress_group)

        self.execute_button = PushButton(FIF.PLAY_SOLID, "执行烧录", self)
        self.execute_button.clicked.connect(self.execute_pyocd_program)
        execute_hlayout = QHBoxLayout()
        execute_hlayout.addWidget(self.execute_button)
        main_pyocd_setting_layout.addLayout(execute_hlayout)

        main_pyocd_setting_layout.setSpacing(12)
        self.pyocd_setting.setLayout(main_pyocd_setting_layout)

        QTimer.singleShot(500, self.scan_probes)
        QTimer.singleShot(500, self.scan_targets)

    def init_more_setting_ui(self):
        more_setting_layout = QVBoxLayout()
        
        self.advanced_group = QGroupBox("高级设置")
        advanced_layout = QVBoxLayout()
        
        self.config_label = BodyLabel("配置文件:")
        self.config_lineedit = LineEdit()
        self.config_lineedit.setPlaceholderText("留空使用默认配置")
        config_hlayout = QHBoxLayout()
        config_hlayout.addWidget(self.config_label)
        config_hlayout.addStretch(1)
        config_hlayout.addWidget(self.config_lineedit)
        advanced_layout.addLayout(config_hlayout)
        
        self.pack_label = BodyLabel("CMSIS Pack:")
        self.pack_lineedit = LineEdit()
        # 使用设置中的 CM pack 路径
        self.pack_lineedit.setText(cfg.get(cfg.cmPackPath))
        self.pack_lineedit.setPlaceholderText("留空使用默认Pack")
        pack_hlayout = QHBoxLayout()
        pack_hlayout.addWidget(self.pack_label)
        pack_hlayout.addStretch(1)
        pack_hlayout.addWidget(self.pack_lineedit)
        advanced_layout.addLayout(pack_hlayout)
        
        self.advanced_group.setLayout(advanced_layout)
        more_setting_layout.addWidget(self.advanced_group)
        
        more_setting_layout.addStretch(1)
        self.more_setting.setLayout(more_setting_layout)
    
    def __updateTheme(self):
        """ 更新主题 """
        is_dark = isDarkTheme()
        text_color = "#ffffff" if is_dark else "#000000"
        
        # 更新所有标签和组框的颜色
        widgets_to_update = [
            getattr(self, 'file_group', None),
            getattr(self, 'target_group', None),
            getattr(self, 'load_group', None),
            getattr(self, 'advanced_group', None),
            getattr(self, 'progress_group', None),
            getattr(self, 'target_label', None),
            getattr(self, 'probe_label', None),
            getattr(self, 'frequency_label', None),
            getattr(self, 'connect_mode_label', None),
            getattr(self, 'erase_label', None),
            getattr(self, 'address_label', None),
            getattr(self, 'config_label', None),
            getattr(self, 'pack_label', None),
            getattr(self, 'progress_label', None),
        ]
        
        for widget in widgets_to_update:
            if widget:
                widget.setStyleSheet(f"color: {text_color};")
    
    def __onTrustCrcChanged(self, state):
        """ CRC检查状态变化 """
        cfg.pyocdTrustCrc.value = state == 2  # 2 is Qt.CheckState.Checked
        cfg.save()

    def scan_probes(self):
        # 不再在这里清空，而是在 on_probes_found 中处理
        self.list_probes_thread = Pyocd_List_Probes_Thread()
        self.list_probes_thread.probes_found.connect(self.on_probes_found)
        self.list_probes_thread.error_occurred.connect(self.on_probes_error)
        self.list_probes_thread.start()

    def scan_targets(self):
        self.list_targets_thread = Pyocd_List_Targets_Thread()
        self.list_targets_thread.targets_found.connect(self.on_targets_found)
        self.list_targets_thread.error_occurred.connect(self.on_targets_error)
        self.list_targets_thread.start()

    def on_probes_found(self, probes):
        # 比较是否有变化
        has_change = False
        if len(probes) != len(self.last_probes_data):
            has_change = True
        else:
            # 比较每个调试器的唯一ID
            for i, probe in enumerate(probes):
                if probe['unique_id'] != self.last_probes_data[i]['unique_id']:
                    has_change = True
                    break
        
        if not has_change:
            # 没有变化，静默处理
            return
        
        self.last_probes_data = probes.copy()
        self.probes_data = probes
        self.probe_combo.clear()
        
        if not probes:
            self.probe_combo.setPlaceholderText("未找到调试器")
            InfoBar.warning(
                title="扫描结果",
                content="未找到连接的调试器",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
        else:
            for probe in probes:
                self.probe_combo.addItem(probe['display'])
            
            InfoBar.success(
                title="扫描完成",
                content=f"找到 {len(probes)} 个调试器",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=2000,
                parent=self,
            )
        


    def on_probes_error(self, error):
        # 检查是否有变化（从有调试器变为无调试器，或从无调试器变为错误状态）
        has_change = False
        if len(self.last_probes_data) > 0:
            has_change = True
        elif self.probe_combo.currentText() or self.probe_combo.placeholderText() != "扫描失败":
            has_change = True
        
        if not has_change:
            # 没有变化，静默处理
            return
        
        self.last_probes_data = []
        self.probe_combo.clear()
        self.probe_combo.setPlaceholderText("扫描失败")
        
        InfoBar.error(
            title="扫描失败",
            content=f"无法扫描调试器: {error}",
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=3000,
            parent=self,
        )
        


    def on_targets_found(self, targets):
        self.targets_data = targets
        self.target_combo.clear()
        self.target_combo.addItems(targets)
        
        # 设置默认值为 stm32f407vgtx
        if "stm32f407vgtx" in targets:
            self.target_combo.setCurrentText("stm32f407vgtx")
        
        if targets:
            InfoBar.success(
                title="目标列表加载完成",
                content=f"已加载 {len(targets)} 个目标类型",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=2000,
                parent=self,
            )

    def on_targets_error(self, error):
        self.target_combo.clear()
        default_targets = [
            "stm32f407vg",
            "stm32f407zg",
            "stm32f411re",
            "stm32f103c8",
        ]
        self.target_combo.addItems(default_targets)
        
        InfoBar.warning(
            title="目标列表加载失败",
            content="使用默认目标列表",
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=2000,
            parent=self,
        )

    def browse_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择固件文件",
            "",
            "固件文件 (*.bin *.hex *.elf);;所有文件 (*.*)"
        )
        if file_path:
            self.file_path_lineedit.setText(file_path)
            # 保存到配置
            cfg.pyocdFirmwarePath.value = file_path
            cfg.save()

    def clear_output(self):
        self.output_area_text.clear()

    def export_output(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出输出",
            "pyocd_output.txt",
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

    def execute_pyocd_program(self):
        if not PYOCD_AVAILABLE:
            InfoBar.error(
                title="错误",
                content="pyocd库未安装，请使用 'pip install pyocd' 安装",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        file_path = self.file_path_lineedit.text().strip()
        if not file_path:
            InfoBar.warning(
                title="错误",
                content="请选择固件文件",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        if not os.path.exists(file_path):
            InfoBar.warning(
                title="错误",
                content="固件文件不存在",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        target = self.target_combo.currentText().strip()
        if not target:
            InfoBar.warning(
                title="错误",
                content="请选择目标类型",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return
        
        probe_uid = None
        probe_index = self.probe_combo.currentIndex()
        if probe_index >= 0 and probe_index < len(self.probes_data):
            probe_uid = self.probes_data[probe_index]['unique_id']
        
        if not probe_uid:
            InfoBar.warning(
                title="错误",
                content="请选择调试器",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return
        
        frequency = self.frequency_combo.currentText()
        connect_mode = self.connect_mode_combo.currentText()
        erase_mode = self.erase_combo.currentText()
        base_address = self.address_lineedit.text().strip() or None
        trust_crc = self.trust_crc_checkbox.isChecked()
        pre_reset = self.pre_reset_checkbox.isChecked()
        no_reset = self.no_reset_checkbox.isChecked()
        config = self.config_lineedit.text().strip() or None
        pack = self.pack_lineedit.text().strip() or None

        self.output_area_text.clear()
        self.output_area_text.appendPlainText("=" * 74)
        self.output_area_text.appendPlainText("开始烧录固件...")
        self.output_area_text.appendPlainText(f"固件文件: {file_path}")
        self.output_area_text.appendPlainText(f"目标类型: {target}")
        self.output_area_text.appendPlainText(f"调试器: {probe_uid}")
        self.output_area_text.appendPlainText(f"SWD频率: {frequency}")
        self.output_area_text.appendPlainText(f"连接模式: {connect_mode}")
        self.output_area_text.appendPlainText(f"擦除方式: {erase_mode}")
        self.output_area_text.appendPlainText("=" * 74)

        self.progress_bar.setValue(0)
        self.progress_label.setText("正在连接设备...")

        self.execute_button.setEnabled(False)
        self.execute_button.setText("烧录中...")

        self.program_thread = Pyocd_Program_Thread(
            file_path=file_path,
            target=target,
            probe_uid=probe_uid,
            frequency=frequency,
            connect_mode=connect_mode,
            erase_mode=erase_mode,
            base_address=base_address,
            trust_crc=trust_crc,
            no_reset=no_reset,
            pre_reset=pre_reset,
            config=config,
            pack=pack
        )
        self.program_thread.output_received.connect(self.on_output_received)
        self.program_thread.error_received.connect(self.on_error_received)
        self.program_thread.finished.connect(self.on_program_finished)
        self.program_thread.progress_updated.connect(self.on_progress_updated)
        self.program_thread.start()

    def on_output_received(self, output):
        self.output_area_text.appendPlainText(output)

    def on_error_received(self, error):
        self.output_area_text.appendPlainText(f"错误: {error}")

    def on_progress_updated(self, progress, total):
        percentage = progress
        self.progress_bar.setValue(percentage)
        self.progress_label.setText(f"烧录进度: {percentage}%")

    def on_program_finished(self, returncode):
        self.output_area_text.appendPlainText("=" * 74)
        if returncode == 0:
            self.output_area_text.appendPlainText("烧录成功完成")
            self.progress_bar.setValue(100)
            self.progress_label.setText("烧录完成")
            InfoBar.success(
                title="烧录成功",
                content="固件已成功烧录到目标设备",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
        else:
            self.output_area_text.appendPlainText("烧录失败")
            self.progress_label.setText("烧录失败")
            InfoBar.error(
                title="烧录失败",
                content="固件烧录过程中出现错误",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
        
        self.execute_button.setEnabled(True)
        self.execute_button.setText("执行烧录")
