# coding:utf-8
import sys
import os
import re
import pathlib
import urllib.parse
from datetime import datetime
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl
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
    PlainTextEdit,
    isDarkTheme,
    CheckBox,
    ProgressBar,
    ComboBox,
    SpinBox,
    CardWidget,
    ScrollArea,
)

from settings.config import cfg

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import cairosvg
    CAIROSVG_AVAILABLE = True
except (ImportError, OSError, Exception):
    CAIROSVG_AVAILABLE = False

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


class LayoutBlockCard(CardWidget):
    def __init__(self, index, selector='', name='', enabled=True, parent=None):
        super().__init__(parent)
        self.index = index
        self.selector = selector
        self.name = name
        self.enabled = enabled
        
        self.setFixedHeight(80)
        self.card_layout = QHBoxLayout(self)
        self.card_layout.setContentsMargins(15, 10, 15, 10)
        self.card_layout.setSpacing(10)
        
        self.enable_checkbox = CheckBox(f"布局块 {index}", self)
        self.enable_checkbox.setChecked(enabled)
        self.card_layout.addWidget(self.enable_checkbox)
        
        self.selector_edit = LineEdit()
        self.selector_edit.setPlaceholderText("CSS选择器 (如: #app, .product-card)")
        self.selector_edit.setText(selector)
        self.selector_edit.setFixedWidth(200)
        self.card_layout.addWidget(self.selector_edit)
        
        self.name_edit = LineEdit()
        self.name_edit.setPlaceholderText("输出文件名")
        self.name_edit.setText(name)
        self.name_edit.setFixedWidth(150)
        self.card_layout.addWidget(self.name_edit)
        
        self.card_layout.addStretch(1)
    
    def get_config(self):
        return {
            'enabled': self.enable_checkbox.isChecked(),
            'selector': self.selector_edit.text().strip(),
            'name': self.name_edit.text().strip() or f"layout_{self.index}"
        }


class PlaywrightExtractThread(QThread):
    progress_updated = pyqtSignal(int, str)
    extract_completed = pyqtSignal(bool, str, list)
    error_occurred = pyqtSignal(str)

    def __init__(self, html_path, output_folder, scale_factor=2,
                 layout_blocks=None, recursive_depth=0, min_size=20,
                 extract_images=False, extract_svg=False, extract_iconify=False):
        super().__init__()
        self.html_path = html_path
        self.output_folder = output_folder
        self.scale_factor = scale_factor
        self.layout_blocks = layout_blocks or []
        self.recursive_depth = recursive_depth
        self.min_size = min_size
        self.extract_images = extract_images
        self.extract_svg = extract_svg
        self.extract_iconify = extract_iconify
        self.extracted_files = []
        self.element_counter = {}

    def run(self):
        if not PLAYWRIGHT_AVAILABLE:
            self.error_occurred.emit("playwright库未安装，请使用 'pip install playwright && playwright install chromium' 安装")
            return

        try:
            if not os.path.exists(self.output_folder):
                os.makedirs(self.output_folder)

            self.progress_updated.emit(5, "正在启动浏览器引擎...")
            
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(device_scale_factor=self.scale_factor)
                
                html_url = pathlib.Path(self.html_path).as_uri()
                self.progress_updated.emit(10, "正在加载HTML页面...")
                page.goto(html_url, wait_until='networkidle', timeout=30000)
                
                page.wait_for_timeout(2000)
                
                elements_to_process = []
                
                for block in self.layout_blocks:
                    if block['enabled'] and block['selector']:
                        try:
                            locator = page.locator(block['selector'])
                            count = locator.count()
                            for i in range(count):
                                el = locator.nth(i)
                                elements_to_process.append({
                                    'element': el,
                                    'type': 'layout',
                                    'name': block['name'],
                                    'depth': 0,
                                    'parent_name': ''
                                })
                        except Exception:
                            pass
                
                if self.extract_images:
                    locator = page.locator('img')
                    count = locator.count()
                    for i in range(count):
                        el = locator.nth(i)
                        elements_to_process.append({
                            'element': el,
                            'type': 'image',
                            'name': '',
                            'depth': 0,
                            'parent_name': ''
                        })
                
                if self.extract_svg:
                    locator = page.locator('svg')
                    count = locator.count()
                    for i in range(count):
                        el = locator.nth(i)
                        elements_to_process.append({
                            'element': el,
                            'type': 'svg',
                            'name': '',
                            'depth': 0,
                            'parent_name': ''
                        })
                
                if self.extract_iconify:
                    locator = page.locator('iconify-icon')
                    count = locator.count()
                    for i in range(count):
                        el = locator.nth(i)
                        elements_to_process.append({
                            'element': el,
                            'type': 'iconify',
                            'name': '',
                            'depth': 0,
                            'parent_name': ''
                        })
                
                if not elements_to_process:
                    browser.close()
                    self.extract_completed.emit(True, "未发现可提取的资源", [])
                    return
                
                self.progress_updated.emit(15, f"发现 {len(elements_to_process)} 个初始元素...")
                
                all_elements = []
                for item in elements_to_process:
                    all_elements.append(item)
                    if self.recursive_depth > 0 and item['type'] == 'layout':
                        self._collect_children_recursive(item['element'], item['name'], 1, all_elements)
                
                total_tasks = len(all_elements)
                self.progress_updated.emit(20, f"递归遍历完成，共 {total_tasks} 个元素待处理...")
                
                success_count = 0
                
                for idx, item in enumerate(all_elements):
                    progress = 20 + int((idx / total_tasks) * 75)
                    el = item['element']
                    
                    try:
                        if not el.is_visible():
                            self.progress_updated.emit(progress, f"跳过不可见元素")
                            continue
                        
                        box = el.bounding_box()
                        if not box or box['width'] == 0 or box['height'] == 0:
                            self.progress_updated.emit(progress, f"跳过零尺寸元素")
                            continue
                        
                        w = int(box['width'])
                        h = int(box['height'])
                        
                        if w < self.min_size or h < self.min_size:
                            self.progress_updated.emit(progress, f"跳过小尺寸元素 ({w}x{h})")
                            continue
                        
                        name = self._generate_element_name(el, item)
                        filename = f"{name}.png"
                        filepath = os.path.join(self.output_folder, filename)
                        
                        self.progress_updated.emit(progress, f"截取 {name} ({w}x{h})")
                        
                        el.screenshot(path=filepath)
                        
                        self.extracted_files.append({
                            'name': filename, 
                            'path': filepath, 
                            'type': item['type'],
                            'width': w,
                            'height': h,
                            'depth': item['depth']
                        })
                        success_count += 1
                        
                    except Exception as e:
                        self.progress_updated.emit(progress, f"跳过元素: {str(e)[:30]}")
                        continue
                
                browser.close()
            
            self.progress_updated.emit(100, "处理完成")
            message = f"成功处理 {success_count}/{total_tasks} 个资源，保存到 {self.output_folder}"
            self.extract_completed.emit(True, message, self.extracted_files)

        except Exception as e:
            self.error_occurred.emit(f"处理失败: {str(e)}")

    def _collect_children_recursive(self, parent_el, parent_name, current_depth, all_elements):
        if current_depth > self.recursive_depth:
            return
        
        try:
            children = parent_el.locator('> *')
            count = children.count()
            
            for i in range(count):
                child = children.nth(i)
                
                try:
                    if not child.is_visible():
                        continue
                    
                    box = child.bounding_box()
                    if not box or box['width'] < self.min_size or box['height'] < self.min_size:
                        continue
                    
                    tag = child.evaluate('el => el.tagName.toLowerCase()')
                    
                    skip_tags = ['script', 'style', 'meta', 'link', 'head', 'title', 'noscript']
                    if tag in skip_tags:
                        continue
                    
                    child_name = self._get_element_identifier(child)
                    full_name = f"{parent_name}_{child_name}" if parent_name else child_name
                    
                    all_elements.append({
                        'element': child,
                        'type': 'layout',
                        'name': full_name,
                        'depth': current_depth,
                        'parent_name': parent_name
                    })
                    
                    self._collect_children_recursive(child, full_name, current_depth + 1, all_elements)
                    
                except Exception:
                    continue
                    
        except Exception:
            pass

    def _get_element_identifier(self, el):
        try:
            id_attr = el.get_attribute('id') or ''
            if id_attr.strip():
                return self._sanitize_filename(id_attr.strip())
            
            class_attr = el.get_attribute('class') or ''
            if class_attr.strip():
                classes = class_attr.strip().split()
                meaningful_classes = [c for c in classes if not c.startswith('w-') and not c.startswith('h-') and len(c) > 2]
                if meaningful_classes:
                    return self._sanitize_filename(meaningful_classes[0])
            
            tag = el.evaluate('el => el.tagName.toLowerCase()')
            return f"{tag}"
            
        except Exception:
            return "element"

    def _generate_element_name(self, el, item):
        if item['name']:
            base_name = self._sanitize_filename(item['name'])
            if base_name not in self.element_counter:
                self.element_counter[base_name] = 0
            self.element_counter[base_name] += 1
            if self.element_counter[base_name] > 1:
                return f"{base_name}_{self.element_counter[base_name]}"
            return base_name
        
        if item['type'] == 'image':
            alt = el.get_attribute('alt') or ''
            if alt.strip():
                return self._sanitize_filename(alt.strip())
            return f"image_{len(self.extracted_files)+1}"
        
        elif item['type'] == 'svg':
            return f"svg_{len(self.extracted_files)+1}"
        
        elif item['type'] == 'iconify':
            icon_name = el.get_attribute('icon') or ''
            if icon_name.strip():
                return f"icon_{self._sanitize_filename(icon_name.replace(':', '_'))}"
            return f"icon_{len(self.extracted_files)+1}"
        
        else:
            identifier = self._get_element_identifier(el)
            depth_prefix = f"L{item['depth']}" if item['depth'] > 0 else ""
            if depth_prefix:
                return f"{depth_prefix}_{identifier}"
            return identifier

    def _sanitize_filename(self, name):
        name = re.sub(r'[<>:"/\\|?* ]', '_', name)
        name = name.strip('_')
        name = re.sub(r'_+', '_', name)
        return name if name else 'unnamed'


class HTML_UI_Extract_Widget(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("html_ui_extract_widget")
        self.resize(1000, 750)
        
        self.Main_hLayout = QHBoxLayout(self)
        self.Main_hLayout.setSpacing(0)
        self.Main_hLayout.setContentsMargins(0, 0, 0, 0)
        
        self.scroll_area = ScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        self.scroll_content = QWidget()
        self.scroll_content.setObjectName("scroll_content")
        self.main_vBoxLayout = QVBoxLayout(self.scroll_content)
        self.main_vBoxLayout.setSpacing(10)
        self.main_vBoxLayout.setContentsMargins(30, 30, 30, 30)
        
        self.extract_thread = None
        self.layout_cards = []
        
        self._init_source_ui()
        self._init_render_ui()
        self._init_layout_blocks_ui()
        self._init_options_ui()
        self._init_progress_ui()
        
        self.main_vBoxLayout.addStretch(1)
        
        self.scroll_area.setWidget(self.scroll_content)
        self.Main_hLayout.addWidget(self.scroll_area, 3)
        self._init_output_bar_ui()
        
        self.__updateTheme()
        cfg.themeChanged.connect(self.__updateTheme)

    def _init_source_ui(self):
        self.source_group = QGroupBox("HTML源文件")
        source_layout = QVBoxLayout()
        source_layout.setSpacing(12)
        
        source_title = StrongBodyLabel("选择本地HTML文件")
        source_layout.addWidget(source_title)
        
        html_label = BodyLabel("HTML文件路径:")
        self.html_path_lineedit = LineEdit()
        self.html_path_lineedit.setPlaceholderText("选择包含UI资源的HTML文件")
        self.browse_html_button = PushButton(FIF.FOLDER, "浏览", self)
        self.browse_html_button.clicked.connect(self._browse_html_file)
        html_hlayout = QHBoxLayout()
        html_hlayout.addWidget(html_label)
        html_hlayout.addWidget(self.html_path_lineedit, 1)
        html_hlayout.addWidget(self.browse_html_button)
        source_layout.addLayout(html_hlayout)
        
        output_label = BodyLabel("输出文件夹:")
        self.output_folder_lineedit = LineEdit()
        self.output_folder_lineedit.setPlaceholderText("LVGL资源输出目录")
        self.browse_output_button = PushButton(FIF.FOLDER, "浏览", self)
        self.browse_output_button.clicked.connect(self._browse_output_folder)
        output_hlayout = QHBoxLayout()
        output_hlayout.addWidget(output_label)
        output_hlayout.addWidget(self.output_folder_lineedit, 1)
        output_hlayout.addWidget(self.browse_output_button)
        source_layout.addLayout(output_hlayout)
        
        self.source_group.setLayout(source_layout)
        self.main_vBoxLayout.addWidget(self.source_group)

    def _init_render_ui(self):
        self.render_group = QGroupBox("渲染设置")
        render_layout = QVBoxLayout()
        render_layout.setSpacing(12)
        
        mode_row = QHBoxLayout()
        mode_label = BodyLabel("渲染模式:")
        self.mode_combo = ComboBox()
        self.mode_combo.addItems(['浏览器渲染 (推荐)', '基础模式'])
        self.mode_combo.setCurrentIndex(0)
        self.mode_combo.setFixedWidth(200)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        mode_row.addWidget(mode_label)
        mode_row.addWidget(self.mode_combo)
        mode_row.addStretch(1)
        render_layout.addLayout(mode_row)
        
        scale_row = QHBoxLayout()
        scale_label = BodyLabel("缩放倍率:")
        self.scale_combo = ComboBox()
        self.scale_combo.addItems(['1x (原始尺寸)', '2x (推荐, 清晰)', '3x (超清)', '4x (极致清晰)'])
        self.scale_combo.setCurrentIndex(1)
        self.scale_combo.setFixedWidth(200)
        scale_row.addWidget(scale_label)
        scale_row.addWidget(self.scale_combo)
        scale_row.addStretch(1)
        render_layout.addLayout(scale_row)
        
        self.mode_note = BodyLabel("浏览器渲染: 截取HTML实际显示效果(含圆角/裁剪/阴影等CSS效果)")
        self.mode_note.setStyleSheet("color: #888;")
        render_layout.addWidget(self.mode_note)
        
        self.render_group.setLayout(render_layout)
        self.main_vBoxLayout.addWidget(self.render_group)

    def _init_layout_blocks_ui(self):
        self.layout_group = QGroupBox("布局截图 (浏览器渲染)")
        layout_layout = QVBoxLayout()
        layout_layout.setSpacing(12)
        
        layout_title = StrongBodyLabel("截取布局块/容器 - 支持递归遍历子元素")
        layout_layout.addWidget(layout_title)
        
        self.enable_layout_checkbox = CheckBox("启用布局截图", self)
        self.enable_layout_checkbox.setChecked(True)
        layout_layout.addWidget(self.enable_layout_checkbox)
        
        recursive_row = QHBoxLayout()
        recursive_label = BodyLabel("递归深度:")
        self.recursive_spinbox = SpinBox()
        self.recursive_spinbox.setRange(0, 10)
        self.recursive_spinbox.setValue(3)
        self.recursive_spinbox.setFixedWidth(150)
        recursive_row.addWidget(recursive_label)
        recursive_row.addWidget(self.recursive_spinbox)
        
        min_size_label = BodyLabel("最小尺寸:")
        self.min_size_spinbox = SpinBox()
        self.min_size_spinbox.setRange(1, 100)
        self.min_size_spinbox.setValue(20)
        self.min_size_spinbox.setFixedWidth(150)
        recursive_row.addWidget(min_size_label)
        recursive_row.addWidget(self.min_size_spinbox)
        recursive_row.addStretch(1)
        layout_layout.addLayout(recursive_row)
        
        recursive_note = BodyLabel("递归深度0=仅截取指定块; 1=截取子元素; 2=截取孙元素...")
        recursive_note.setStyleSheet("color: #888;")
        layout_layout.addWidget(recursive_note)
        
        preset_row = QHBoxLayout()
        preset_label = BodyLabel("快速添加预设:")
        self.preset_combo = ComboBox()
        self.preset_combo.addItems([
            '主容器 (#app)',
            '商品卡片',
            '导航栏',
            '底部栏',
            'Banner区域',
            '商品行',
            '商品网格',
        ])
        self.preset_combo.setFixedWidth(200)
        preset_row.addWidget(preset_label)
        preset_row.addWidget(self.preset_combo)
        
        self.add_preset_button = PushButton(FIF.ADD, "添加", self)
        self.add_preset_button.clicked.connect(self._add_preset_block)
        preset_row.addWidget(self.add_preset_button)
        
        self.auto_detect_button = PushButton(FIF.SEARCH, "自动检测", self)
        self.auto_detect_button.clicked.connect(self._auto_detect_layouts)
        preset_row.addWidget(self.auto_detect_button)
        
        preset_row.addStretch(1)
        layout_layout.addLayout(preset_row)
        
        blocks_title_row = QHBoxLayout()
        blocks_title = BodyLabel("布局块列表:")
        blocks_title_row.addWidget(blocks_title)
        
        self.add_block_button = PushButton(FIF.ADD, "添加块", self)
        self.add_block_button.clicked.connect(self._add_layout_block)
        blocks_title_row.addWidget(self.add_block_button)
        
        self.clear_blocks_button = PushButton(FIF.DELETE, "清空", self)
        self.clear_blocks_button.clicked.connect(self._clear_layout_blocks)
        blocks_title_row.addWidget(self.clear_blocks_button)
        
        blocks_title_row.addStretch(1)
        layout_layout.addLayout(blocks_title_row)
        
        self.blocks_container = QWidget()
        self.blocks_vlayout = QVBoxLayout(self.blocks_container)
        self.blocks_vlayout.setSpacing(8)
        self.blocks_vlayout.setContentsMargins(0, 0, 0, 0)
        layout_layout.addWidget(self.blocks_container)
        
        self._add_default_blocks()
        
        self.layout_note = BodyLabel("提示: 递归遍历会自动提取所有嵌套的子布局块，文件名按层级命名")
        self.layout_note.setStyleSheet("color: #888;")
        layout_layout.addWidget(self.layout_note)
        
        self.layout_group.setLayout(layout_layout)
        self.main_vBoxLayout.addWidget(self.layout_group)

    def _add_default_blocks(self):
        default_blocks = [
            {'selector': '#app', 'name': 'main', 'enabled': True},
        ]
        for block in default_blocks:
            self._add_layout_block(block['selector'], block['name'], block['enabled'])

    def _add_layout_block(self, selector='', name='', enabled=True):
        index = len(self.layout_cards) + 1
        card = LayoutBlockCard(index, selector, name, enabled, self)
        self.layout_cards.append(card)
        self.blocks_vlayout.addWidget(card)

    def _add_preset_block(self):
        presets = {
            '主容器 (#app)': ('#app', 'main'),
            '商品卡片': ('.bg-white.rounded-xl', 'card'),
            '导航栏': ('nav', 'nav'),
            '底部栏': ('footer', 'footer'),
            'Banner区域': ('.min-w-full', 'banner'),
            '商品行': ('.flex.flex-row', 'row'),
            '商品网格': ('.grid', 'grid'),
        }
        preset_name = self.preset_combo.currentText()
        if preset_name in presets:
            selector, name = presets[preset_name]
            self._add_layout_block(selector, name, True)

    def _auto_detect_layouts(self):
        if not self.html_path_lineedit.text().strip():
            InfoBar.warning(title="提示", content="请先选择HTML文件", orient=Qt.Orientation.Horizontal, isClosable=True, position=InfoBarPosition.TOP, duration=2000, parent=self)
            return
        
        self._clear_layout_blocks()
        
        auto_selectors = [
            ('#app', 'main'),
            ('header', 'header'),
            ('nav', 'nav'),
            ('footer', 'footer'),
            ('main', 'content'),
            ('section', 'section'),
        ]
        
        for selector, name in auto_selectors:
            self._add_layout_block(selector, name, True)
        
        InfoBar.success(title="自动检测", content=f"已添加 {len(self.layout_cards)} 个布局块", orient=Qt.Orientation.Horizontal, isClosable=True, position=InfoBarPosition.TOP, duration=2000, parent=self)

    def _clear_layout_blocks(self):
        for card in self.layout_cards:
            card.deleteLater()
        self.layout_cards.clear()

    def _init_options_ui(self):
        self.options_group = QGroupBox("元素提取选项")
        options_layout = QVBoxLayout()
        options_layout.setSpacing(12)
        
        options_title = StrongBodyLabel("选择要提取的单个元素类型")
        options_layout.addWidget(options_title)
        
        checkbox_row1 = QHBoxLayout()
        self.extract_images_checkbox = CheckBox("图片 (img标签)", self)
        self.extract_images_checkbox.setChecked(False)
        checkbox_row1.addWidget(self.extract_images_checkbox)
        
        self.extract_svg_checkbox = CheckBox("内联SVG", self)
        self.extract_svg_checkbox.setChecked(False)
        checkbox_row1.addWidget(self.extract_svg_checkbox)
        
        self.extract_iconify_checkbox = CheckBox("Iconify图标", self)
        self.extract_iconify_checkbox.setChecked(False)
        checkbox_row1.addWidget(self.extract_iconify_checkbox)
        
        checkbox_row1.addStretch(1)
        options_layout.addLayout(checkbox_row1)
        
        self.options_note = BodyLabel("提示: 启用布局截图后，单个元素提取可选")
        self.options_note.setStyleSheet("color: #888;")
        options_layout.addWidget(self.options_note)
        
        self.options_group.setLayout(options_layout)
        self.main_vBoxLayout.addWidget(self.options_group)

    def _init_progress_ui(self):
        self.progress_group = QGroupBox("进度")
        progress_layout = QVBoxLayout()
        progress_layout.setSpacing(8)
        
        self.progress_bar = ProgressBar()
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)
        
        self.progress_label = BodyLabel("准备就绪")
        progress_layout.addWidget(self.progress_label)
        
        button_layout = QHBoxLayout()
        self.extract_button = PushButton(FIF.DOWNLOAD, "开始提取", self)
        self.extract_button.clicked.connect(self._execute_extract)
        button_layout.addWidget(self.extract_button)
        
        self.open_folder_button = PushButton(FIF.FOLDER, "打开输出文件夹", self)
        self.open_folder_button.clicked.connect(self._open_output_folder)
        button_layout.addWidget(self.open_folder_button)
        
        button_layout.addStretch(1)
        progress_layout.addLayout(button_layout)
        
        self.progress_group.setLayout(progress_layout)
        self.main_vBoxLayout.addWidget(self.progress_group)

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

    def _on_mode_changed(self, index):
        if index == 0:
            self.layout_group.setEnabled(True)
            self.mode_note.setText("浏览器渲染: 截取HTML实际显示效果(含圆角/裁剪/阴影等CSS效果)")
            if not PLAYWRIGHT_AVAILABLE:
                self.mode_note.setText("⚠️ playwright未安装，请运行: pip install playwright && playwright install chromium")
                self.mode_note.setStyleSheet("color: #e74c3c;")
            else:
                self.mode_note.setStyleSheet("color: #888;")
        else:
            self.layout_group.setEnabled(False)
            self.mode_note.setText("基础模式: 下载资源并按HTML属性调整尺寸(不含CSS渲染效果，不支持布局截图)")
            self.mode_note.setStyleSheet("color: #888;")

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
            getattr(self, 'source_group', None),
            getattr(self, 'render_group', None),
            getattr(self, 'layout_group', None),
            getattr(self, 'options_group', None),
            getattr(self, 'progress_group', None),
        ]
        
        for widget in widgets_to_update:
            if widget:
                widget.setStyleSheet(f"color: {text_color};")

    def _browse_html_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择HTML文件", "", "HTML文件 (*.html *.htm);;所有文件 (*.*)"
        )
        if file_path:
            self.html_path_lineedit.setText(file_path)
            if not self.output_folder_lineedit.text():
                base_dir = os.path.dirname(file_path)
                output_dir = os.path.join(base_dir, "lvgl_resources")
                self.output_folder_lineedit.setText(output_dir)
            self._log(f"选择HTML文件: {file_path}")

    def _browse_output_folder(self):
        folder_path = QFileDialog.getExistingDirectory(self, "选择输出文件夹")
        if folder_path:
            self.output_folder_lineedit.setText(folder_path)
            self._log(f"输出文件夹: {folder_path}")

    def _log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.output_area_text.appendPlainText(f"[{timestamp}] {message}")

    def _clear_output(self):
        self.output_area_text.clear()

    def _export_output(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出输出", "lvgl_extract_output.txt", "文本文件 (*.txt);;所有文件 (*)"
        )
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(self.output_area_text.toPlainText())
                InfoBar.success(title="导出成功", content=f"输出已保存到 {file_path}", orient=Qt.Orientation.Horizontal, isClosable=True, position=InfoBarPosition.TOP, duration=3000, parent=self)
            except Exception as e:
                InfoBar.error(title="导出失败", content=str(e), orient=Qt.Orientation.Horizontal, isClosable=True, position=InfoBarPosition.TOP, duration=3000, parent=self)

    def _open_output_folder(self):
        output_folder = self.output_folder_lineedit.text()
        if output_folder and os.path.exists(output_folder):
            from PyQt6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl.fromLocalFile(output_folder))
        else:
            InfoBar.warning(title="警告", content="输出文件夹不存在", orient=Qt.Orientation.Horizontal, isClosable=True, position=InfoBarPosition.TOP, duration=3000, parent=self)

    def _get_scale_factor(self):
        idx = self.scale_combo.currentIndex()
        return [1, 2, 3, 4][idx]

    def _get_layout_blocks_config(self):
        blocks = []
        for card in self.layout_cards:
            config = card.get_config()
            if config['enabled'] and config['selector']:
                blocks.append(config)
        return blocks

    def _execute_extract(self):
        html_path = self.html_path_lineedit.text().strip()
        if not html_path:
            InfoBar.warning(title="警告", content="请选择HTML文件", orient=Qt.Orientation.Horizontal, isClosable=True, position=InfoBarPosition.TOP, duration=3000, parent=self)
            return
        
        if not os.path.exists(html_path):
            InfoBar.warning(title="警告", content="HTML文件不存在", orient=Qt.Orientation.Horizontal, isClosable=True, position=InfoBarPosition.TOP, duration=3000, parent=self)
            return
        
        output_folder = self.output_folder_lineedit.text().strip()
        if not output_folder:
            InfoBar.warning(title="警告", content="请选择输出文件夹", orient=Qt.Orientation.Horizontal, isClosable=True, position=InfoBarPosition.TOP, duration=3000, parent=self)
            return
        
        use_playwright = self.mode_combo.currentIndex() == 0
        scale_factor = self._get_scale_factor()
        
        if use_playwright and not PLAYWRIGHT_AVAILABLE:
            InfoBar.error(title="错误", content="playwright未安装，请运行: pip install playwright && playwright install chromium", orient=Qt.Orientation.Horizontal, isClosable=True, position=InfoBarPosition.TOP, duration=5000, parent=self)
            return
        
        layout_blocks = self._get_layout_blocks_config() if self.enable_layout_checkbox.isChecked() else []
        recursive_depth = self.recursive_spinbox.value()
        min_size = self.min_size_spinbox.value()
        
        if self.enable_layout_checkbox.isChecked() and not layout_blocks:
            InfoBar.warning(title="提示", content="请至少启用一个布局块", orient=Qt.Orientation.Horizontal, isClosable=True, position=InfoBarPosition.TOP, duration=3000, parent=self)
            return
        
        self.output_area_text.clear()
        self._log("=" * 60)
        self._log("开始LVGL资源提取...")
        self._log(f"HTML文件: {html_path}")
        self._log(f"输出目录: {output_folder}")
        self._log(f"渲染模式: {'浏览器渲染' if use_playwright else '基础模式'}")
        self._log(f"缩放倍率: {scale_factor}x")
        self._log(f"布局截图: {'是' if self.enable_layout_checkbox.isChecked() else '否'} ({len(layout_blocks)}个根块)")
        self._log(f"递归深度: {recursive_depth} (0=仅根块)")
        self._log(f"最小尺寸: {min_size}px")
        for block in layout_blocks:
            self._log(f"  - {block['name']}: {block['selector']}")
        self._log(f"提取图片: {'是' if self.extract_images_checkbox.isChecked() else '否'}")
        self._log(f"提取SVG: {'是' if self.extract_svg_checkbox.isChecked() else '否'}")
        self._log(f"提取Iconify: {'是' if self.extract_iconify_checkbox.isChecked() else '否'}")
        self._log("=" * 60)
        
        self.progress_bar.setValue(0)
        self.progress_label.setText("正在处理...")
        self.extract_button.setEnabled(False)
        self.extract_button.setText("处理中...")
        
        self.extract_thread = PlaywrightExtractThread(
            html_path=html_path,
            output_folder=output_folder,
            scale_factor=scale_factor,
            layout_blocks=layout_blocks,
            recursive_depth=recursive_depth,
            min_size=min_size,
            extract_images=self.extract_images_checkbox.isChecked(),
            extract_svg=self.extract_svg_checkbox.isChecked(),
            extract_iconify=self.extract_iconify_checkbox.isChecked()
        )
        self.extract_thread.progress_updated.connect(self._on_progress_updated)
        self.extract_thread.extract_completed.connect(self._on_extract_completed)
        self.extract_thread.error_occurred.connect(self._on_error_occurred)
        self.extract_thread.start()

    def _on_progress_updated(self, progress, message):
        self.progress_bar.setValue(progress)
        self.progress_label.setText(message)
        self._log(message)

    def _on_extract_completed(self, success, message, extracted_files):
        self.extract_button.setEnabled(True)
        self.extract_button.setText("开始提取")
        
        self._log("=" * 60)
        self._log(message)
        
        if extracted_files:
            self._log("提取文件列表:")
            depth_groups = {}
            for f in extracted_files:
                depth = f.get('depth', 0)
                if depth not in depth_groups:
                    depth_groups[depth] = []
                depth_groups[depth].append(f)
            
            for depth in sorted(depth_groups.keys()):
                self._log(f"  --- 层级 {depth} ---")
                for f in depth_groups[depth]:
                    w = f.get('width', '')
                    h = f.get('height', '')
                    type_str = f.get('type', '')
                    if w and h:
                        self._log(f"    [{type_str}] {f['name']} ({w}x{h})")
                    else:
                        self._log(f"    [{type_str}] {f['name']}")
        
        self._log("=" * 60)
        
        if success:
            self.progress_bar.setValue(100)
            self.progress_label.setText("提取完成")
            InfoBar.success(title="提取完成", content=message, orient=Qt.Orientation.Horizontal, isClosable=True, position=InfoBarPosition.TOP, duration=5000, parent=self)

    def _on_error_occurred(self, error):
        self.extract_button.setEnabled(True)
        self.extract_button.setText("开始提取")
        self.progress_label.setText("提取失败")
        self._log(f"错误: {error}")
        InfoBar.error(title="提取失败", content=error, orient=Qt.Orientation.Horizontal, isClosable=True, position=InfoBarPosition.TOP, duration=3000, parent=self)


if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    w = HTML_UI_Extract_Widget()
    w.show()
    sys.exit(app.exec())