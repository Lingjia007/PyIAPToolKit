# coding:utf-8
import sys
import os
import json
import uuid
import struct
from datetime import datetime
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl, QTimer
from PyQt6.QtGui import QDesktopServices, QPixmap, QImage
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFileDialog,
    QGroupBox,
    QGridLayout,
    QLabel,
    QGraphicsOpacityEffect,
)
from PyQt6.QtCore import QPropertyAnimation, QEasingCurve

import serial.tools.list_ports

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
    SpinBox,
    TextEdit,
    HyperlinkButton,
    ScrollArea,
    ToolButton,
)

from settings.config import cfg

try:
    from alipay import AliPay
    ALIPAY_AVAILABLE = True
except ImportError:
    ALIPAY_AVAILABLE = False

try:
    import qrcode
    QRCODE_AVAILABLE = True
except ImportError:
    QRCODE_AVAILABLE = False


class TradeQueryThread(QThread):
    result_ready = pyqtSignal(bool, str)
    error_occurred = pyqtSignal(str)

    def __init__(self, alipay_client, out_trade_no):
        super().__init__()
        self.alipay_client = alipay_client
        self.out_trade_no = out_trade_no

    def run(self):
        try:
            response = self.alipay_client.api_alipay_trade_query(
                out_trade_no=self.out_trade_no
            )
            self.result_ready.emit(True, json.dumps(response, ensure_ascii=False, indent=2))
        except Exception as e:
            self.error_occurred.emit(str(e))


class TradeRefundThread(QThread):
    result_ready = pyqtSignal(bool, str)
    error_occurred = pyqtSignal(str)

    def __init__(self, alipay_client, out_trade_no, refund_amount, refund_reason=None, out_request_no=None):
        super().__init__()
        self.alipay_client = alipay_client
        self.out_trade_no = out_trade_no
        self.refund_amount = refund_amount
        self.refund_reason = refund_reason
        self.out_request_no = out_request_no

    def run(self):
        try:
            kwargs = {
                'out_trade_no': self.out_trade_no,
                'refund_amount': self.refund_amount,
            }
            if self.refund_reason:
                kwargs['refund_reason'] = self.refund_reason
            if self.out_request_no:
                kwargs['out_request_no'] = self.out_request_no

            response = self.alipay_client.api_alipay_trade_refund(**kwargs)
            self.result_ready.emit(True, json.dumps(response, ensure_ascii=False, indent=2))
        except Exception as e:
            self.error_occurred.emit(str(e))


class TradeCloseThread(QThread):
    result_ready = pyqtSignal(bool, str)
    error_occurred = pyqtSignal(str)

    def __init__(self, alipay_client, out_trade_no):
        super().__init__()
        self.alipay_client = alipay_client
        self.out_trade_no = out_trade_no

    def run(self):
        try:
            response = self.alipay_client.api_alipay_trade_close(
                out_trade_no=self.out_trade_no
            )
            self.result_ready.emit(True, json.dumps(response, ensure_ascii=False, indent=2))
        except Exception as e:
            self.error_occurred.emit(str(e))


class TradePayThread(QThread):
    """条码支付(被扫)线程，商户扫用户付款码"""
    result_ready = pyqtSignal(bool, str)
    error_occurred = pyqtSignal(str)

    def __init__(self, alipay_client, auth_code, total_amount, subject, out_trade_no=None):
        super().__init__()
        self.alipay_client = alipay_client
        self.auth_code = auth_code
        self.total_amount = total_amount
        self.subject = subject
        self.out_trade_no = out_trade_no

    def run(self):
        try:
            kwargs = {
                'auth_code': self.auth_code,
                'scene': 'bar_code',
                'total_amount': self.total_amount,
                'subject': self.subject,
            }
            if self.out_trade_no:
                kwargs['out_trade_no'] = self.out_trade_no
            response = self.alipay_client.api_alipay_trade_pay(**kwargs)
            self.result_ready.emit(True, json.dumps(response, ensure_ascii=False, indent=2))
        except Exception as e:
            self.error_occurred.emit(str(e))


class PrecreateThread(QThread):
    """当面付预下单线程，获取二维码链接并生成二维码图片"""
    result_ready = pyqtSignal(bool, str, str, object)  # success, qr_code, out_trade_no, qimage
    error_occurred = pyqtSignal(str)

    def __init__(self, alipay_client, out_trade_no, total_amount, subject, timeout="5m"):
        super().__init__()
        self.alipay_client = alipay_client
        self.out_trade_no = out_trade_no
        self.total_amount = total_amount
        self.subject = subject
        self.timeout = timeout
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        try:
            if not self._running:
                return
            result = self.alipay_client.api_alipay_trade_precreate(
                out_trade_no=self.out_trade_no,
                total_amount=self.total_amount,
                subject=self.subject,
                timeout_express=self.timeout,
            )
            if not self._running:
                return
            if result.get("code") == "10000":
                qr_code = result.get("qr_code", "")
                # 在线程中生成二维码图片
                qimage = None
                if qr_code and QRCODE_AVAILABLE and self._running:
                    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M,
                                       box_size=8, border=2)
                    qr.add_data(qr_code)
                    qr.make(fit=True)
                    img = qr.make_image(fill_color="black", back_color="white")
                    if img.mode != "RGB":
                        img = img.convert("RGB")
                    buf = img.tobytes("raw", "RGB")
                    qimage = QImage(buf, img.size[0], img.size[1], 3 * img.size[0], QImage.Format.Format_RGB888).copy()
                if self._running:
                    self.result_ready.emit(True, qr_code, self.out_trade_no, qimage)
            else:
                if self._running:
                    self.error_occurred.emit(f"接口返回错误: {result.get('sub_msg', result.get('msg', '未知错误'))}")
        except Exception as e:
            if self._running:
                self.error_occurred.emit(str(e))


class PollTradeThread(QThread):
    """轮询订单支付状态线程"""
    trade_status = pyqtSignal(str, str)  # status, trade_no
    error_occurred = pyqtSignal(str)

    def __init__(self, alipay_client, out_trade_no, max_times=60, interval=3):
        super().__init__()
        self.alipay_client = alipay_client
        self.out_trade_no = out_trade_no
        self.max_times = max_times
        self.interval = interval
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        consecutive_errors = 0
        for i in range(self.max_times):
            if not self._running:
                break
            try:
                result = self.alipay_client.api_alipay_trade_query(
                    out_trade_no=self.out_trade_no
                )
                consecutive_errors = 0
                trade_status = result.get("trade_status", "")
                if trade_status == "TRADE_SUCCESS":
                    self.trade_status.emit("TRADE_SUCCESS", self.out_trade_no)
                    return
                elif trade_status == "TRADE_FINISHED":
                    self.trade_status.emit("TRADE_FINISHED", self.out_trade_no)
                    return
                elif trade_status == "TRADE_CLOSED":
                    self.trade_status.emit("TRADE_CLOSED", self.out_trade_no)
                    return
            except Exception as e:
                consecutive_errors += 1
                if consecutive_errors >= 5:
                    self.error_occurred.emit(f"连续{consecutive_errors}次查询失败: {str(e)}")
                    return
                # 单次超时/网络异常，继续重试
            # 分段sleep，及时响应stop请求
            for _ in range(self.interval * 10):
                if not self._running:
                    return
                self.msleep(100)
        self.trade_status.emit("WAIT_TIMEOUT", self.out_trade_no)


class SerialReceiveThread(QThread):
    """串口接收线程，解析开发板发来的请求帧"""
    request_received = pyqtSignal(int, bytes)  # cmd, data

    def __init__(self, serial_conn):
        super().__init__()
        self.serial_conn = serial_conn
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        rx_buf = bytearray()
        while self._running:
            try:
                if self.serial_conn and self.serial_conn.is_open:
                    n = self.serial_conn.in_waiting
                    if n > 0:
                        rx_buf.extend(self.serial_conn.read(n))
                    # 尝试解析帧: AA 55 CMD LEN_H LEN_L DATA... 0D 0A
                    while len(rx_buf) >= 7:  # 最小帧长: 头2+cmd1+len2+尾2
                        # 查找帧头
                        if rx_buf[0] != 0xAA or rx_buf[1] != 0x55:
                            rx_buf.pop(0)
                            continue
                        cmd = rx_buf[2]
                        data_len = (rx_buf[3] << 8) | rx_buf[4]
                        frame_len = 2 + 1 + 2 + data_len + 2
                        if len(rx_buf) < frame_len:
                            break
                        # 校验帧尾
                        if rx_buf[frame_len - 2] != 0x0D or rx_buf[frame_len - 1] != 0x0A:
                            rx_buf.pop(0)
                            continue
                        data = bytes(rx_buf[5:5 + data_len])
                        self.request_received.emit(cmd, data)
                        rx_buf = rx_buf[frame_len:]
                    # 缓冲区过长时截断
                    if len(rx_buf) > 4096:
                        rx_buf.clear()
                else:
                    self.msleep(100)
                    continue
            except Exception:
                self.msleep(50)
            self.msleep(10)


class AlipaySandbox_Widget(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("alipay_sandbox_widget")
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
        self.main_vBoxLayout = QVBoxLayout(self.scroll_content)
        self.main_vBoxLayout.setSpacing(10)
        self.main_vBoxLayout.setContentsMargins(30, 30, 30, 30)

        self.alipay_client = None
        self.query_thread = None
        self.refund_thread = None
        self.close_thread = None
        self.precreate_thread = None
        self.poll_thread = None
        self.trade_pay_thread = None
        self.current_qr_trade_no = None
        self.current_qr_code = None
        self.serial_conn = None
        self.serial_rx_thread = None

        self._init_config_ui()
        self._init_qr_payment_ui()
        self._init_barcode_payment_ui()
        self._init_payment_ui()
        self._init_query_ui()
        self._init_refund_ui()
        self._init_close_ui()
        self._init_account_info_ui()

        self.main_vBoxLayout.addStretch(1)

        self.scroll_area.setWidget(self.scroll_content)
        self.Main_hLayout.addWidget(self.scroll_area, 3)
        self._init_output_bar_ui()

        # 预填沙盒默认密钥
        self._set_default_keys()

        # 刷新串口列表
        self._refresh_serial_ports()

        self.__updateTheme()
        cfg.themeChanged.connect(self.__updateTheme)

    def _init_config_ui(self):
        self.config_group = QGroupBox("沙盒配置")
        config_layout = QVBoxLayout()
        config_layout.setSpacing(12)

        config_title = StrongBodyLabel("应用配置")
        config_layout.addWidget(config_title)

        appid_layout = QHBoxLayout()
        appid_label = BodyLabel("APPID:")
        self.appid_lineedit = LineEdit()
        self.appid_lineedit.setPlaceholderText("沙盒应用APPID")
        self.appid_lineedit.setText("9021000164610522")
        appid_layout.addWidget(appid_label)
        appid_layout.addWidget(self.appid_lineedit, 1)
        config_layout.addLayout(appid_layout)

        pid_layout = QHBoxLayout()
        pid_label = BodyLabel("商户PID:")
        self.pid_lineedit = LineEdit()
        self.pid_lineedit.setPlaceholderText("商户PID")
        self.pid_lineedit.setText("2088721101731232")
        pid_layout.addWidget(pid_label)
        pid_layout.addWidget(self.pid_lineedit, 1)
        config_layout.addLayout(pid_layout)

        key_layout = QHBoxLayout()
        key_label = BodyLabel("应用私钥:")
        self.key_textedit = TextEdit()
        self.key_textedit.setPlaceholderText("应用私钥(RSA2)，支持PEM格式或纯Base64")
        self.key_textedit.setFixedHeight(60)
        self.load_key_button = PushButton(FIF.FOLDER, "加载", self)
        self.load_key_button.clicked.connect(self._load_private_key)
        key_layout.addWidget(key_label)
        key_layout.addWidget(self.key_textedit, 1)
        key_layout.addWidget(self.load_key_button)
        config_layout.addLayout(key_layout)

        pubkey_layout = QHBoxLayout()
        pubkey_label = BodyLabel("支付宝公钥:")
        self.pubkey_textedit = TextEdit()
        self.pubkey_textedit.setPlaceholderText("支付宝公钥(用于验签)，支持PEM格式或纯Base64")
        self.pubkey_textedit.setFixedHeight(60)
        self.load_pubkey_button = PushButton(FIF.FOLDER, "加载", self)
        self.load_pubkey_button.clicked.connect(self._load_alipay_public_key)
        pubkey_layout.addWidget(pubkey_label)
        pubkey_layout.addWidget(self.pubkey_textedit, 1)
        pubkey_layout.addWidget(self.load_pubkey_button)
        config_layout.addLayout(pubkey_layout)

        gateway_layout = QHBoxLayout()
        gateway_label = BodyLabel("网关地址:")
        self.gateway_lineedit = LineEdit()
        self.gateway_lineedit.setPlaceholderText("支付宝网关地址")
        self.gateway_lineedit.setText("https://openapi-sandbox.dl.alipaydev.com/gateway.do")
        gateway_layout.addWidget(gateway_label)
        gateway_layout.addWidget(self.gateway_lineedit, 1)
        config_layout.addLayout(gateway_layout)

        sign_type_layout = QHBoxLayout()
        sign_type_label = BodyLabel("签名方式:")
        self.sign_type_combo = ComboBox()
        self.sign_type_combo.addItems(["RSA2", "RSA"])
        self.sign_type_combo.setCurrentIndex(0)
        sign_type_layout.addWidget(sign_type_label)
        sign_type_layout.addWidget(self.sign_type_combo, 1)
        config_layout.addLayout(sign_type_layout)

        self.init_client_button = PushButton(FIF.SYNC, "初始化客户端", self)
        self.init_client_button.clicked.connect(self._init_client)
        config_layout.addWidget(self.init_client_button)

        self.config_group.setLayout(config_layout)
        self.main_vBoxLayout.addWidget(self.config_group)

    def _init_qr_payment_ui(self):
        self.qr_payment_group = QGroupBox("扫码支付(当面付)")
        qr_layout = QVBoxLayout()
        qr_layout.setSpacing(12)

        qr_title = StrongBodyLabel("生成付款二维码")
        qr_layout.addWidget(qr_title)

        qr_subject_layout = QHBoxLayout()
        qr_subject_label = BodyLabel("商品名称:")
        self.qr_subject_lineedit = LineEdit()
        self.qr_subject_lineedit.setPlaceholderText("商品名称")
        self.qr_subject_lineedit.setText("LVGL售货机商品")
        qr_subject_layout.addWidget(qr_subject_label)
        qr_subject_layout.addWidget(self.qr_subject_lineedit, 1)
        qr_layout.addLayout(qr_subject_layout)

        qr_amount_layout = QHBoxLayout()
        qr_amount_label = BodyLabel("支付金额:")
        self.qr_amount_lineedit = LineEdit()
        self.qr_amount_lineedit.setPlaceholderText("金额(元)")
        self.qr_amount_lineedit.setText("0.01")
        qr_amount_layout.addWidget(qr_amount_label)
        qr_amount_layout.addWidget(self.qr_amount_lineedit, 1)
        qr_layout.addLayout(qr_amount_layout)

        qr_trade_layout = QHBoxLayout()
        qr_trade_label = BodyLabel("订单号:")
        self.qr_trade_lineedit = LineEdit()
        self.qr_trade_lineedit.setPlaceholderText("商户订单号(留空自动生成)")
        qr_trade_layout.addWidget(qr_trade_label)
        qr_trade_layout.addWidget(self.qr_trade_lineedit, 1)
        qr_layout.addLayout(qr_trade_layout)

        qr_timeout_layout = QHBoxLayout()
        qr_timeout_label = BodyLabel("超时时间:")
        self.qr_timeout_combo = ComboBox()
        self.qr_timeout_combo.addItems(["1m", "3m", "5m", "10m", "15m", "30m"])
        self.qr_timeout_combo.setCurrentIndex(2)
        qr_timeout_layout.addWidget(qr_timeout_label)
        qr_timeout_layout.addWidget(self.qr_timeout_combo, 1)
        qr_layout.addLayout(qr_timeout_layout)

        self.create_qr_button = PushButton(FIF.QRCODE, "生成付款二维码", self)
        self.create_qr_button.clicked.connect(self._create_qr_payment)
        qr_layout.addWidget(self.create_qr_button)

        # 二维码显示区域
        qr_display_layout = QHBoxLayout()
        self.qr_code_label = QLabel()
        self.qr_code_label.setFixedSize(200, 200)
        self.qr_code_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_code_label.setStyleSheet("border: 1px dashed #ccc; border-radius: 4px;")
        self.qr_code_label.setText("二维码将在此显示")
        qr_display_layout.addStretch(1)
        qr_display_layout.addWidget(self.qr_code_label)
        qr_display_layout.addStretch(1)
        qr_layout.addLayout(qr_display_layout)

        # 支付状态
        self.qr_status_label = StrongBodyLabel("")
        self.qr_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        qr_layout.addWidget(self.qr_status_label)

        # 订单号显示
        self.qr_trade_no_label = BodyLabel("")
        self.qr_trade_no_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        qr_layout.addWidget(self.qr_trade_no_label)

        qr_btn_layout = QHBoxLayout()
        self.save_qr_button = PushButton(FIF.SAVE, "保存二维码", self)
        self.save_qr_button.clicked.connect(self._save_qr_code)
        self.save_qr_button.setEnabled(False)
        self.poll_status_button = PushButton(FIF.SYNC, "轮询支付状态", self)
        self.poll_status_button.clicked.connect(self._start_poll)
        self.poll_status_button.setEnabled(False)
        qr_btn_layout.addStretch(1)
        qr_btn_layout.addWidget(self.save_qr_button)
        qr_btn_layout.addWidget(self.poll_status_button)
        qr_btn_layout.addStretch(1)
        qr_layout.addLayout(qr_btn_layout)

        # 串口传输区域
        serial_title = StrongBodyLabel("串口传输到开发板")
        qr_layout.addWidget(serial_title)

        serial_port_layout = QHBoxLayout()
        serial_port_label = BodyLabel("串口:")
        self.serial_port_combo = ComboBox()
        self.serial_port_combo.setPlaceholderText("选择串口")
        self.refresh_serial_button = PushButton(FIF.SYNC, "刷新", self)
        self.refresh_serial_button.setFixedWidth(80)
        self.refresh_serial_button.clicked.connect(self._refresh_serial_ports)
        serial_port_layout.addWidget(serial_port_label)
        serial_port_layout.addWidget(self.serial_port_combo, 1)
        serial_port_layout.addWidget(self.refresh_serial_button)
        qr_layout.addLayout(serial_port_layout)

        serial_baud_layout = QHBoxLayout()
        serial_baud_label = BodyLabel("波特率:")
        self.serial_baud_combo = ComboBox()
        self.serial_baud_combo.addItems(["9600", "19200", "38400", "57600", "115200", "230400", "460800", "921600"])
        self.serial_baud_combo.setCurrentIndex(4)  # 115200
        serial_baud_layout.addWidget(serial_baud_label)
        serial_baud_layout.addWidget(self.serial_baud_combo, 1)
        qr_layout.addLayout(serial_baud_layout)

        self.serial_connect_button = PushButton(FIF.LINK, "打开串口", self)
        self.serial_connect_button.clicked.connect(self._toggle_serial)
        qr_layout.addWidget(self.serial_connect_button)

        self.send_to_device_button = PushButton(FIF.SEND, "发送二维码到设备", self)
        self.send_to_device_button.clicked.connect(self._send_qr_to_device)
        self.send_to_device_button.setEnabled(False)
        qr_layout.addWidget(self.send_to_device_button)

        protocol_hint = BodyLabel("协议: 帧头 0xAA 0x55 | 命令字 | 数据长度(2B) | 数据 | 帧尾 0x0D 0x0A")
        protocol_hint.setStyleSheet("color: #888; font-size: 11px;")
        qr_layout.addWidget(protocol_hint)

        self.qr_payment_group.setLayout(qr_layout)
        self.main_vBoxLayout.addWidget(self.qr_payment_group)

    def _init_barcode_payment_ui(self):
        self.barcode_payment_group = QGroupBox("条码支付(被扫)")
        barcode_layout = QVBoxLayout()
        barcode_layout.setSpacing(12)

        barcode_title = StrongBodyLabel("商户扫用户付款码")
        barcode_layout.addWidget(barcode_title)

        auth_code_layout = QHBoxLayout()
        auth_code_label = BodyLabel("付款码:")
        self.auth_code_lineedit = LineEdit()
        self.auth_code_lineedit.setPlaceholderText("用户支付宝付款码数字(18~28位)")
        auth_code_layout.addWidget(auth_code_label)
        auth_code_layout.addWidget(self.auth_code_lineedit, 1)
        barcode_layout.addLayout(auth_code_layout)

        barcode_subject_layout = QHBoxLayout()
        barcode_subject_label = BodyLabel("商品名称:")
        self.barcode_subject_lineedit = LineEdit()
        self.barcode_subject_lineedit.setPlaceholderText("商品名称")
        self.barcode_subject_lineedit.setText("LVGL售货机商品")
        barcode_subject_layout.addWidget(barcode_subject_label)
        barcode_subject_layout.addWidget(self.barcode_subject_lineedit, 1)
        barcode_layout.addLayout(barcode_subject_layout)

        barcode_amount_layout = QHBoxLayout()
        barcode_amount_label = BodyLabel("支付金额:")
        self.barcode_amount_lineedit = LineEdit()
        self.barcode_amount_lineedit.setPlaceholderText("金额(元)")
        self.barcode_amount_lineedit.setText("0.01")
        barcode_amount_layout.addWidget(barcode_amount_label)
        barcode_amount_layout.addWidget(self.barcode_amount_lineedit, 1)
        barcode_layout.addLayout(barcode_amount_layout)

        barcode_trade_layout = QHBoxLayout()
        barcode_trade_label = BodyLabel("订单号:")
        self.barcode_trade_lineedit = LineEdit()
        self.barcode_trade_lineedit.setPlaceholderText("商户订单号(留空自动生成)")
        barcode_trade_layout.addWidget(barcode_trade_label)
        barcode_trade_layout.addWidget(self.barcode_trade_lineedit, 1)
        barcode_layout.addLayout(barcode_trade_layout)

        self.barcode_pay_button = PushButton(FIF.SHOPPING_CART, "发起条码支付", self)
        self.barcode_pay_button.clicked.connect(self._barcode_pay)
        barcode_layout.addWidget(self.barcode_pay_button)

        # 条码支付状态
        self.barcode_status_label = StrongBodyLabel("")
        self.barcode_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        barcode_layout.addWidget(self.barcode_status_label)

        barcode_hint = BodyLabel("设备扫描用户付款码后，通过串口发送付款码数字(CMD=0x85)即可自动发起支付")
        barcode_hint.setStyleSheet("color: #888; font-size: 11px;")
        barcode_hint.setWordWrap(True)
        barcode_layout.addWidget(barcode_hint)

        self.barcode_payment_group.setLayout(barcode_layout)
        self.main_vBoxLayout.addWidget(self.barcode_payment_group)

    def _init_payment_ui(self):
        self.payment_group = QGroupBox("电脑网站支付")
        payment_layout = QVBoxLayout()
        payment_layout.setSpacing(12)

        payment_title = StrongBodyLabel("创建支付订单")
        payment_layout.addWidget(payment_title)

        subject_layout = QHBoxLayout()
        subject_label = BodyLabel("订单标题:")
        self.subject_lineedit = LineEdit()
        self.subject_lineedit.setPlaceholderText("商品名称")
        self.subject_lineedit.setText("测试商品")
        subject_layout.addWidget(subject_label)
        subject_layout.addWidget(self.subject_lineedit, 1)
        payment_layout.addLayout(subject_layout)

        amount_layout = QHBoxLayout()
        amount_label = BodyLabel("订单金额:")
        self.amount_lineedit = LineEdit()
        self.amount_lineedit.setPlaceholderText("金额(元)")
        self.amount_lineedit.setText("0.01")
        amount_layout.addWidget(amount_label)
        amount_layout.addWidget(self.amount_lineedit, 1)
        payment_layout.addLayout(amount_layout)

        out_trade_layout = QHBoxLayout()
        out_trade_label = BodyLabel("订单号:")
        self.out_trade_lineedit = LineEdit()
        self.out_trade_lineedit.setPlaceholderText("商户订单号(留空自动生成)")
        out_trade_layout.addWidget(out_trade_label)
        out_trade_layout.addWidget(self.out_trade_lineedit, 1)
        payment_layout.addLayout(out_trade_layout)

        return_url_layout = QHBoxLayout()
        return_url_label = BodyLabel("回调地址:")
        self.return_url_lineedit = LineEdit()
        self.return_url_lineedit.setPlaceholderText("支付完成回调URL(可选)")
        return_url_layout.addWidget(return_url_label)
        return_url_layout.addWidget(self.return_url_lineedit, 1)
        payment_layout.addLayout(return_url_layout)

        self.create_payment_button = PushButton(FIF.SHOPPING_CART, "生成支付链接", self)
        self.create_payment_button.clicked.connect(self._create_payment)
        payment_layout.addWidget(self.create_payment_button)

        self.payment_group.setLayout(payment_layout)
        self.main_vBoxLayout.addWidget(self.payment_group)

    def _init_query_ui(self):
        self.query_group = QGroupBox("订单查询")
        query_layout = QVBoxLayout()
        query_layout.setSpacing(12)

        query_trade_layout = QHBoxLayout()
        query_trade_label = BodyLabel("订单号:")
        self.query_trade_lineedit = LineEdit()
        self.query_trade_lineedit.setPlaceholderText("商户订单号")
        query_trade_layout.addWidget(query_trade_label)
        query_trade_layout.addWidget(self.query_trade_lineedit, 1)
        query_layout.addLayout(query_trade_layout)

        self.query_button = PushButton(FIF.SEARCH, "查询订单", self)
        self.query_button.clicked.connect(self._query_trade)
        query_layout.addWidget(self.query_button)

        self.query_group.setLayout(query_layout)
        self.main_vBoxLayout.addWidget(self.query_group)

    def _init_refund_ui(self):
        self.refund_group = QGroupBox("订单退款")
        refund_layout = QVBoxLayout()
        refund_layout.setSpacing(12)

        refund_trade_layout = QHBoxLayout()
        refund_trade_label = BodyLabel("订单号:")
        self.refund_trade_lineedit = LineEdit()
        self.refund_trade_lineedit.setPlaceholderText("商户订单号")
        refund_trade_layout.addWidget(refund_trade_label)
        refund_trade_layout.addWidget(self.refund_trade_lineedit, 1)
        refund_layout.addLayout(refund_trade_layout)

        refund_amount_layout = QHBoxLayout()
        refund_amount_label = BodyLabel("退款金额:")
        self.refund_amount_lineedit = LineEdit()
        self.refund_amount_lineedit.setPlaceholderText("退款金额(元)")
        refund_amount_layout.addWidget(refund_amount_label)
        refund_amount_layout.addWidget(self.refund_amount_lineedit, 1)
        refund_layout.addLayout(refund_amount_layout)

        refund_reason_layout = QHBoxLayout()
        refund_reason_label = BodyLabel("退款原因:")
        self.refund_reason_lineedit = LineEdit()
        self.refund_reason_lineedit.setPlaceholderText("退款原因(可选)")
        refund_reason_layout.addWidget(refund_reason_label)
        refund_reason_layout.addWidget(self.refund_reason_lineedit, 1)
        refund_layout.addLayout(refund_reason_layout)

        self.refund_button = PushButton(FIF.RETURN, "执行退款", self)
        self.refund_button.clicked.connect(self._refund_trade)
        refund_layout.addWidget(self.refund_button)

        self.refund_group.setLayout(refund_layout)
        self.main_vBoxLayout.addWidget(self.refund_group)

    def _init_close_ui(self):
        self.close_group = QGroupBox("关闭订单")
        close_layout = QVBoxLayout()
        close_layout.setSpacing(12)

        close_trade_layout = QHBoxLayout()
        close_trade_label = BodyLabel("订单号:")
        self.close_trade_lineedit = LineEdit()
        self.close_trade_lineedit.setPlaceholderText("商户订单号")
        close_trade_layout.addWidget(close_trade_label)
        close_trade_layout.addWidget(self.close_trade_lineedit, 1)
        close_layout.addLayout(close_trade_layout)

        self.close_button = PushButton(FIF.CLOSE, "关闭订单", self)
        self.close_button.clicked.connect(self._close_trade)
        close_layout.addWidget(self.close_button)

        self.close_group.setLayout(close_layout)
        self.main_vBoxLayout.addWidget(self.close_group)

    def _init_account_info_ui(self):
        self.account_group = QGroupBox("沙盒账号")
        account_layout = QVBoxLayout()
        account_layout.setSpacing(8)

        merchant_title = StrongBodyLabel("商家信息")
        account_layout.addWidget(merchant_title)

        merchant_info = [
            ("商户账号:", "calmwf0076@sandbox.com"),
            ("登录密码:", "111111"),
            ("商户PID:", "2088721101731232"),
            ("账户余额:", "1000000.00"),
        ]
        for label_text, value_text in merchant_info:
            row = QHBoxLayout()
            label = BodyLabel(label_text)
            value = LineEdit()
            value.setText(value_text)
            value.setReadOnly(True)
            copy_btn = PushButton(FIF.COPY, "复制", self)
            copy_btn.setFixedWidth(120)
            copy_btn.clicked.connect(lambda checked, v=value: self._copy_text(v.text()))
            row.addWidget(label)
            row.addWidget(value, 1)
            row.addWidget(copy_btn)
            account_layout.addLayout(row)

        buyer_title = StrongBodyLabel("买家信息")
        account_layout.addWidget(buyer_title)

        buyer_info = [
            ("买家账号:", "fgiywn5632@sandbox.com"),
            ("登录密码:", "111111"),
            ("支付密码:", "111111"),
            ("用户UID:", "2088722101731246"),
            ("用户名称:", "fgiywn5632"),
            ("账户余额:", "1000000.00"),
        ]
        for label_text, value_text in buyer_info:
            row = QHBoxLayout()
            label = BodyLabel(label_text)
            value = LineEdit()
            value.setText(value_text)
            value.setReadOnly(True)
            copy_btn = PushButton(FIF.COPY, "复制", self)
            copy_btn.setFixedWidth(120)
            copy_btn.clicked.connect(lambda checked, v=value: self._copy_text(v.text()))
            row.addWidget(label)
            row.addWidget(value, 1)
            row.addWidget(copy_btn)
            account_layout.addLayout(row)

        self.account_group.setLayout(account_layout)
        self.main_vBoxLayout.addWidget(self.account_group)

    def _init_output_bar_ui(self):
        self.right_vBoxLayout = QVBoxLayout()
        self.right_vBoxLayout.setSpacing(0)
        self.right_vBoxLayout.setContentsMargins(0, 10, 10, 10)

        self.toggle_log_btn = ToolButton(FIF.RIGHT_ARROW, self)
        self.toggle_log_btn.setFixedSize(24, 24)
        self.toggle_log_btn.clicked.connect(self._toggle_log_panel)

        self.output_bar_widget = QWidget()
        self.output_bar_vBoxLayout = QVBoxLayout(self.output_bar_widget)
        self.output_bar_vBoxLayout.setContentsMargins(5, 0, 5, 0)

        header_layout = QHBoxLayout()
        header_label = BodyLabel("日志输出")
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

        self.right_vBoxLayout.addWidget(self.toggle_log_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        self.right_vBoxLayout.addWidget(self.output_bar_widget, 1)
        self.Main_hLayout.addLayout(self.right_vBoxLayout, 0)

        self.log_visible = True
        self.target_log_width = 350
        self.output_bar_widget.setFixedWidth(self.target_log_width)

        self.opacity_effect = QGraphicsOpacityEffect(self.output_bar_widget)
        self.output_bar_widget.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(1.0)

        self.opacity_animation = None

    def _toggle_log_panel(self):
        self.log_visible = not self.log_visible

        if self.opacity_animation:
            self.opacity_animation.stop()

        self.opacity_animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.opacity_animation.setDuration(150)
        self.opacity_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)

        if self.log_visible:
            self.toggle_log_btn.setIcon(FIF.RIGHT_ARROW)
            self.output_bar_widget.setFixedWidth(self.target_log_width)
            self.opacity_animation.setStartValue(0.0)
            self.opacity_animation.setEndValue(1.0)
        else:
            self.toggle_log_btn.setIcon(FIF.LEFT_ARROW)
            self.opacity_animation.setStartValue(1.0)
            self.opacity_animation.setEndValue(0.0)
            self.opacity_animation.finished.connect(lambda: self.output_bar_widget.setFixedWidth(0))

        self.opacity_animation.start()

    def __updateTheme(self):
        is_dark = isDarkTheme()
        text_color = "#ffffff" if is_dark else "#000000"
        bg_color = "#202020" if is_dark else "#f5f5f5"

        widgets_to_update = [
            getattr(self, 'config_group', None),
            getattr(self, 'qr_payment_group', None),
            getattr(self, 'barcode_payment_group', None),
            getattr(self, 'payment_group', None),
            getattr(self, 'query_group', None),
            getattr(self, 'refund_group', None),
            getattr(self, 'close_group', None),
            getattr(self, 'account_group', None),
        ]

        for widget in widgets_to_update:
            if widget:
                widget.setStyleSheet(f"color: {text_color};")

        self.scroll_content.setStyleSheet(f"background: {bg_color};")
        self.scroll_area.setStyleSheet(
            f"QScrollArea {{ border: none; background: transparent; }}"
        )

    def _copy_text(self, text):
        from PyQt6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        InfoBar.success(
            title="已复制",
            content=text,
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=1500,
            parent=self,
        )

    def _log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.output_area_text.appendPlainText(f"[{timestamp}] {message}")

    def _clear_output(self):
        self.output_area_text.clear()

    def _export_output(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出输出", "alipay_sandbox_output.txt", "文本文件 (*.txt);;所有文件 (*)"
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

    def _refresh_serial_ports(self):
        self.serial_port_combo.clear()
        ports = serial.tools.list_ports.comports()
        for port in ports:
            self.serial_port_combo.addItem(f"{port.device} - {port.description}")
        if ports:
            self.serial_port_combo.setCurrentIndex(0)

    def _get_selected_port_name(self):
        text = self.serial_port_combo.currentText()
        if not text:
            return None
        return text.split(" - ")[0].strip()

    def _toggle_serial(self):
        if self.serial_conn and self.serial_conn.is_open:
            # 停止接收线程
            if self.serial_rx_thread and self.serial_rx_thread.isRunning():
                self.serial_rx_thread.stop()
                self.serial_rx_thread.wait(2000)
            self.serial_conn.close()
            self.serial_conn = None
            self.serial_connect_button.setText("打开串口")
            self.serial_connect_button.setIcon(FIF.LINK)
            self.send_to_device_button.setEnabled(False)
            self._log("串口已关闭")
            InfoBar.info(title="串口已关闭", content="",
                orient=Qt.Orientation.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=2000, parent=self)
        else:
            port_name = self._get_selected_port_name()
            if not port_name:
                InfoBar.warning(title="警告", content="请选择串口",
                    orient=Qt.Orientation.Horizontal, isClosable=True,
                    position=InfoBarPosition.TOP, duration=3000, parent=self)
                return
            baud = int(self.serial_baud_combo.currentText())
            try:
                import serial as pyserial
                self.serial_conn = pyserial.Serial(port_name, baud, timeout=1)
                self.serial_connect_button.setText("关闭串口")
                self.serial_connect_button.setIcon(FIF.CANCEL)
                self.send_to_device_button.setEnabled(True)
                self._log(f"串口已打开: {port_name} @ {baud}")
                InfoBar.success(title="串口已打开", content=f"{port_name} @ {baud}",
                    orient=Qt.Orientation.Horizontal, isClosable=True,
                    position=InfoBarPosition.TOP, duration=3000, parent=self)
                # 启动接收线程
                self.serial_rx_thread = SerialReceiveThread(self.serial_conn)
                self.serial_rx_thread.request_received.connect(self._on_serial_request)
                self.serial_rx_thread.start()
            except Exception as e:
                self._log(f"串口打开失败: {str(e)}")
                InfoBar.error(title="打开失败", content=str(e),
                    orient=Qt.Orientation.Horizontal, isClosable=True,
                    position=InfoBarPosition.TOP, duration=3000, parent=self)

    def _build_frame(self, cmd, data):
        """
        构建通信帧:
        帧头: 0xAA 0x55
        命令字: 1字节
        数据长度: 2字节(大端)
        数据: 变长
        帧尾: 0x0D 0x0A
        """
        header = bytes([0xAA, 0x55])
        tail = bytes([0x0D, 0x0A])
        length = struct.pack('>H', len(data))
        return header + bytes([cmd]) + length + data + tail

    def _send_qr_to_device(self):
        if not self.serial_conn or not self.serial_conn.is_open:
            InfoBar.warning(title="警告", content="请先打开串口",
                orient=Qt.Orientation.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=3000, parent=self)
            return

        if not self.current_qr_code:
            InfoBar.warning(title="警告", content="请先生成二维码",
                orient=Qt.Orientation.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=3000, parent=self)
            return

        try:
            # 命令字 0x01: 发送二维码URL
            qr_data = self.current_qr_code.encode('utf-8')
            frame = self._build_frame(0x01, qr_data)
            self.serial_conn.write(frame)
            self._log(f"已发送二维码到设备, 数据长度: {len(qr_data)} 字节")
            self._log(f"帧数据(hex): {frame[:20].hex()}...")
            InfoBar.success(title="发送成功", content=f"二维码已发送到设备 ({len(qr_data)}B)",
                orient=Qt.Orientation.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=3000, parent=self)
        except Exception as e:
            self._log(f"发送失败: {str(e)}")
            InfoBar.error(title="发送失败", content=str(e),
                orient=Qt.Orientation.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=3000, parent=self)

    def _send_payment_status_to_device(self, status):
        """发送支付状态到设备, 命令字 0x02"""
        if not self.serial_conn or not self.serial_conn.is_open:
            return
        try:
            status_map = {
                "TRADE_SUCCESS": 0x01,
                "TRADE_FINISHED": 0x02,
                "TRADE_CLOSED": 0x03,
                "WAIT_TIMEOUT": 0x04,
            }
            status_byte = status_map.get(status, 0x00)
            frame = self._build_frame(0x02, bytes([status_byte]))
            self.serial_conn.write(frame)
            self._log(f"已发送支付状态到设备: {status} (0x{status_byte:02X})")
        except Exception as e:
            self._log(f"发送状态失败: {str(e)}")

    def _barcode_pay(self):
        """条码支付(被扫): 商户扫用户付款码"""
        if not self.alipay_client:
            InfoBar.warning(title="警告", content="请先初始化客户端",
                orient=Qt.Orientation.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=3000, parent=self)
            return

        # 停止上一次条码支付线程
        if self.trade_pay_thread and self.trade_pay_thread.isRunning():
            self.trade_pay_thread.quit()
            self.trade_pay_thread.wait(1000)

        auth_code = self.auth_code_lineedit.text().strip()
        subject = self.barcode_subject_lineedit.text().strip()
        amount = self.barcode_amount_lineedit.text().strip()
        out_trade_no = self.barcode_trade_lineedit.text().strip()

        if not auth_code:
            InfoBar.warning(title="警告", content="请输入付款码",
                orient=Qt.Orientation.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=3000, parent=self)
            return

        if not subject:
            InfoBar.warning(title="警告", content="请输入商品名称",
                orient=Qt.Orientation.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=3000, parent=self)
            return

        if not amount:
            InfoBar.warning(title="警告", content="请输入支付金额",
                orient=Qt.Orientation.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=3000, parent=self)
            return

        if not out_trade_no:
            out_trade_no = datetime.now().strftime("%Y%m%d%H%M%S") + str(uuid.uuid4().int)[:6]

        self.barcode_pay_button.setEnabled(False)
        self.barcode_status_label.setText("正在发起条码支付...")
        self.barcode_status_label.setStyleSheet("")
        self._log(f"条码支付: 付款码={auth_code}, 金额={amount}, 商品={subject}, 订单号={out_trade_no}")

        self.trade_pay_thread = TradePayThread(
            self.alipay_client, auth_code, amount, subject, out_trade_no
        )
        self.trade_pay_thread.result_ready.connect(self._on_barcode_pay_result)
        self.trade_pay_thread.error_occurred.connect(self._on_barcode_pay_error)
        self.trade_pay_thread.start()

    def _on_barcode_pay_result(self, success, result):
        self.barcode_pay_button.setEnabled(True)
        self._log(f"条码支付结果:\n{result}")
        try:
            result_dict = json.loads(result)
            code = result_dict.get("code", "")
            trade_no = result_dict.get("trade_no", "")
            if code == "10000":
                self.barcode_status_label.setText("支付成功!")
                self.barcode_status_label.setStyleSheet("color: #10b981; font-size: 16px;")
                self._log(f"条码支付成功! 支付宝交易号: {trade_no}")
                InfoBar.success(title="支付成功", content=f"交易号: {trade_no}",
                    orient=Qt.Orientation.Horizontal, isClosable=True,
                    position=InfoBarPosition.TOP, duration=5000, parent=self)
                # 通知设备支付成功
                self._send_payment_status_to_device("TRADE_SUCCESS")
            elif code == "10003":
                self.barcode_status_label.setText("支付处理中...")
                self.barcode_status_label.setStyleSheet("color: #f59e0b; font-size: 16px;")
                self._log("条码支付处理中，需要用户确认")
            else:
                sub_msg = result_dict.get("sub_msg", result_dict.get("msg", "未知错误"))
                self.barcode_status_label.setText(f"支付失败: {sub_msg}")
                self.barcode_status_label.setStyleSheet("color: #ef4444; font-size: 16px;")
                self._log(f"条码支付失败: {sub_msg}")
                InfoBar.error(title="支付失败", content=sub_msg,
                    orient=Qt.Orientation.Horizontal, isClosable=True,
                    position=InfoBarPosition.TOP, duration=5000, parent=self)
        except json.JSONDecodeError:
            self.barcode_status_label.setText("支付结果解析失败")
            self.barcode_status_label.setStyleSheet("color: #ef4444; font-size: 16px;")

    def _on_barcode_pay_error(self, error):
        self.barcode_pay_button.setEnabled(True)
        self.barcode_status_label.setText("支付请求失败")
        self.barcode_status_label.setStyleSheet("color: #ef4444; font-size: 16px;")
        self._log(f"条码支付异常: {error}")
        InfoBar.error(title="请求失败", content=error,
            orient=Qt.Orientation.Horizontal, isClosable=True,
            position=InfoBarPosition.TOP, duration=5000, parent=self)

    def _on_serial_request(self, cmd, data):
        """处理开发板发来的请求帧"""
        cmd_names = {
            0x81: "请求生成二维码",
            0x82: "请求查询支付状态",
            0x83: "请求关闭订单",
            0x84: "心跳",
            0x85: "条码支付(付款码)",
        }
        cmd_name = cmd_names.get(cmd, "未知命令")
        # 完整帧hex
        full_frame = self._build_frame(cmd, data)
        hex_str = ' '.join(f'{b:02X}' for b in full_frame)
        self._log(f"[RX] {cmd_name} (CMD=0x{cmd:02X})")
        self._log(f"  原始帧: {hex_str}")
        if data:
            try:
                text = data.replace(b'\x00', b'|').decode('utf-8', errors='replace')
                self._log(f"  数据(文本): {text}")
            except UnicodeDecodeError:
                pass
            self._log(f"  数据(hex): {data.hex()}")

        if cmd == 0x81:
            # 设备请求生成二维码: data = 商品名称(UTF-8) + 0x00 + 金额(ASCII)
            try:
                null_idx = data.index(0x00)
                name_bytes = data[:null_idx]
                amount_bytes = data[null_idx + 1:]
                subject = name_bytes.decode('utf-8')
                amount = amount_bytes.decode('ascii')
                self._log(f"  解析: 商品={subject}, 金额={amount}")
                # 自动填入并生成
                self.qr_subject_lineedit.setText(subject)
                self.qr_amount_lineedit.setText(amount)
                self.qr_trade_lineedit.clear()
                self._create_qr_payment()
            except (ValueError, UnicodeDecodeError) as e:
                self._log(f"  解析失败: {str(e)}")

        elif cmd == 0x82:
            # 设备请求查询支付状态
            if self.current_qr_trade_no:
                self._log(f"  当前订单: {self.current_qr_trade_no}")
                self._start_poll()
            else:
                self._log("  无当前订单可查询")

        elif cmd == 0x83:
            # 设备请求关闭订单
            if self.current_qr_trade_no:
                self._log(f"  关闭订单: {self.current_qr_trade_no}")
                self._close_trade()
            else:
                self._log("  无当前订单可关闭")

        elif cmd == 0x84:
            # 设备心跳/连接确认
            # 回复心跳
            if self.serial_conn and self.serial_conn.is_open:
                frame = self._build_frame(0x04, bytes([0x01]))
                self.serial_conn.write(frame)
                self._log(f"  已回复心跳")

        elif cmd == 0x85:
            # 设备扫描用户付款码: data = 付款码数字(ASCII) + [0x00 + 金额(ASCII)] + [0x00 + 商品名称(UTF-8)]
            try:
                parts = data.split(b'\x00')
                auth_code = parts[0].decode('ascii').strip()
                amount = parts[1].decode('ascii').strip() if len(parts) > 1 else None
                subject = parts[2].decode('utf-8').strip() if len(parts) > 2 else None
                self._log(f"  解析: 付款码={auth_code}, 金额={amount}, 商品={subject}")
                # 填入UI
                self.auth_code_lineedit.setText(auth_code)
                if amount:
                    self.barcode_amount_lineedit.setText(amount)
                if subject:
                    self.barcode_subject_lineedit.setText(subject)
                self.barcode_trade_lineedit.clear()
                # 自动发起条码支付
                self._barcode_pay()
            except (ValueError, UnicodeDecodeError, IndexError) as e:
                self._log(f"  付款码解析失败: {str(e)}")

        else:
            self._log(f"  未知请求: CMD=0x{cmd:02X}")

    def _set_default_keys(self):
        """预填沙盒默认密钥"""
        default_private_key = (
            "MIIEogIBAAKCAQEAgnM77kzCChIqKpm+6dOxsMAKnihOAHC1nBNFlAeXD5EjyOXs5pid0Xfr4hSIeXRnTtpsXTQF4p43KyatbAIxT9iV9BzWlzHbR3gki0d7hbHgnLhQMTpswdJZiLTYOqQN/FFumLbgJzYK/625fXZsX8U9wO1P7IcAdgKxxZxB0WYYwxuPSYbAxG8l9eHI5iQSDSqQwDyLxPgTqWH9buiqN9IWIwOIqDFb5Kds1TO03+vstsk36Fd1VnpQ+y9wnzDy/+7BMbCapr5YthErtLa7gWwZQE28A3y+t249A4HZFzuQIxMSNadm408PdkVEnWUN4dpfCKvu2M3FzKkuIRHoYQIDAQABAoIBABAaXXmLLCDGIUJk/DYtFbA15JmlbAuN3j1H+7zMOw+G4R35lAbbLBAhd5LO6hHkFqSbPek7dMaGtVS0T5AXrTKoD8q0jKDZXLIz2H8A8fSNAqcV8YBCMA61AqxndpG2kqtk+fwMBxuQBkeNkGo2ZiZkWL0qDkWqXJo0tvEn2tAYVyVNQWoehYeB2L57Flp5jzwHwyeLsxc35PUjjJxITf4OY04/TyiEdxR2cz+RAPIN3Ev/TV/MFvd+VTbhR6bLo3/N7s0/I6cWOjuiT53s8wzPBifDXzztcIzotls6hHvHys0vmcUtFPVMQEC6QU4XtviNvTqzpRaZySVm5AHwg+ECgYEAwETBi6oGSbgHdeOEwrruLyhXeEQ7gY2YwdmYg1S/2QGrzx8JoOWTUxU2xQ1W/1pnH99o0Ha1u+jHJ9Gs+sjSd1nu3yIDcmcZnN6ElHokdWvCf6su3VFjIEo+wW8UJwkfQJUy8KVzLZmcXaWqXdohEkylS3nSOcEXeLJskmYQDuUCgYEArbDHiwQRiEMK1hjzXrj6d9LRuqZxe4k8YQgItalZ64claVxeve6tfUtPP5ut3BgBRs1DX/Drv0OirvpYKsaBmTi4GGNohkmVYFT4A6I4HurAOf4hXqeSpF1S0hisO7J1+LEtcFUQ56JjubHk8oX4ck16w2vjRUFDwgVp8PQDX80CgYB1iBJATBk36zU0TXaUiyyayzBdJmix01rz9Q4UCjSUdT8Ph8uc/XnHqgom/vaVdi/f/fPWqxqA2dUUdEonq6dsqh8pa2NsBbZUfHnTQa8T0GG/JWeqhtvvmzMtj7dj/WGLWykejiUQVPyPCnxQjsz0oMHSl495Gp48e+V+wMFEOQKBgDNXSeSBs1z/1Dgs7+NT8lVw76WohWrqyfo0kb6A7J9+N0TJlQe3gXjDxg0bS2z/e4EeM4gsgsLqjzABuAYM30oXRfOPjtoC7jCnbRhF3yjkYyXBRMPh7KrBGzYXLPIIcm6skK3ftzuA+NFvECnQB/xhgqQ5Q9i4zfqP9xzORCERAoGAHEyfYFu9FrsygGWjjvJuKWYhHjIlrkp/VjxqMHrfNHl/KVqrSAIxSCZPYcWhMTs+7BKHBXWouTdtV06pybxFmup2C+Pc8eUnHGsKPjoGUzaWrhc04zz65XTjh10OU/hKpyfyuP65/gHdz191SC9ZwaophQAFwj2Z1rWISRJa1Ss="
        )
        default_alipay_public_key = (
            "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAh1mRfmjFvTmcvFI3BZDPTI0Z3KbalHGsrdP6ZkD5QnkHiJ69KHCukuAhCgKguhAyecs3QhqqGqB5dYSRTxHRyTUCfjH1BhvQdaUPGT0HNUswQhUF2Wr0LkYCwhdNSyLlrgYVteMc1GKuExImIpG0BE3fD2HDBkz38ZxOkGdpqJTx8XhIrhliGcf2ZhpDU7TcO19uqRr33Iirl/TzJClP3P2+VZ2W+DhdHSHh/qFrbaUvv6HgmGwl7Ktttj6mbsoviZ1bwqU2Nh/stokEZbyUSqD9xYofoDC86xj4P9Y7bQLruhwzqmQ9RBd7X3/lICFlao6ULT8ZP6spaf7fla0pXwIDAQAB"
        )
        self.key_textedit.setPlainText(default_private_key)
        self.pubkey_textedit.setPlainText(default_alipay_public_key)

    def _ensure_pem(self, key_str, key_type):
        """确保密钥为PEM格式，如果只有Base64内容则自动补全PEM头尾"""
        if not key_str:
            return key_str
        if "-----BEGIN" in key_str:
            return key_str
        # 纯Base64，自动补全PEM格式
        lines = [key_str[i:i+64] for i in range(0, len(key_str), 64)]
        return f"-----BEGIN {key_type}-----\n" + "\n".join(lines) + f"\n-----END {key_type}-----\n"

    def _load_private_key(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "加载应用私钥", "", "私钥文件 (*.pem *.key *.txt);;所有文件 (*)"
        )
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                self.key_textedit.setPlainText(content)
                self._log(f"应用私钥已加载: {file_path}")
                InfoBar.success(
                    title="加载成功",
                    content="应用私钥已加载",
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=3000,
                    parent=self,
                )
            except Exception as e:
                InfoBar.error(
                    title="加载失败",
                    content=str(e),
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=3000,
                    parent=self,
                )

    def _load_alipay_public_key(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "加载支付宝公钥", "", "公钥文件 (*.pem *.key *.txt);;所有文件 (*)"
        )
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                self.pubkey_textedit.setPlainText(content)
                self._log(f"支付宝公钥已加载: {file_path}")
                InfoBar.success(
                    title="加载成功",
                    content="支付宝公钥已加载",
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=3000,
                    parent=self,
                )
            except Exception as e:
                InfoBar.error(
                    title="加载失败",
                    content=str(e),
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=3000,
                    parent=self,
                )

    def _warmup_client(self):
        """预热SDK：提前建立SSL连接和DNS缓存，避免首次请求慢"""
        import threading
        def _do_warmup():
            try:
                import urllib3
                gateway = self.gateway_lineedit.text().strip()
                # 预建连接池
                http = urllib3.PoolManager(timeout=urllib3.Timeout(connect=5, read=5))
                http.request("GET", gateway, retries=False)
                http.clear()
                self._log("SDK预热完成")
            except Exception:
                self._log("SDK预热跳过（不影响使用）")
        t = threading.Thread(target=_do_warmup, daemon=True)
        t.start()

    def _init_client(self):
        if not ALIPAY_AVAILABLE:
            InfoBar.error(
                title="错误",
                content="python-alipay-sdk未安装，请使用 'pip install python-alipay-sdk --upgrade' 安装",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        appid = self.appid_lineedit.text().strip()
        private_key = self._ensure_pem(self.key_textedit.toPlainText().strip(), "PRIVATE KEY")
        alipay_public_key = self._ensure_pem(self.pubkey_textedit.toPlainText().strip(), "PUBLIC KEY")
        gateway = self.gateway_lineedit.text().strip()
        sign_type = self.sign_type_combo.currentText()

        if not appid:
            InfoBar.warning(
                title="警告",
                content="请输入APPID",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        if not private_key:
            InfoBar.warning(
                title="警告",
                content="请输入或加载应用私钥",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        if not alipay_public_key:
            InfoBar.warning(
                title="警告",
                content="请输入或加载支付宝公钥",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        try:
            self.alipay_client = AliPay(
                appid=appid,
                app_private_key_string=private_key,
                alipay_public_key_string=alipay_public_key,
                sign_type=sign_type,
                debug=gateway != "https://openapi.alipay.com/gateway.do",
            )
            self._log(f"客户端初始化成功")
            self._log(f"APPID: {appid}")
            self._log(f"签名方式: {sign_type}")
            self._log(f"网关: {gateway}")

            # 预热SDK：提前建立SSL连接，避免首次请求慢
            self._warmup_client()

            InfoBar.success(
                title="初始化成功",
                content="支付宝沙盒客户端已初始化",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
        except Exception as e:
            self._log(f"客户端初始化失败: {str(e)}")
            InfoBar.error(
                title="初始化失败",
                content=str(e),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )

    def _create_qr_payment(self):
        if not self.alipay_client:
            InfoBar.warning(
                title="警告",
                content="请先初始化客户端",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        if not QRCODE_AVAILABLE:
            InfoBar.error(
                title="错误",
                content="qrcode库未安装，请使用 'pip install qrcode[pil]' 安装",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        # 停止之前的轮询线程（不阻塞等待，让旧线程自行退出）
        if self.poll_thread and self.poll_thread.isRunning():
            self.poll_thread.stop()

        # 停止之前的预创建线程（不阻塞等待）
        if self.precreate_thread and self.precreate_thread.isRunning():
            self.precreate_thread.stop()

        # 清除之前的状态
        self.current_qr_code = None
        self.current_qr_trade_no = None
        self.qr_code_label.clear()
        self.qr_status_label.setText("正在生成二维码...")
        self.qr_status_label.setStyleSheet("")
        self.qr_trade_no_label.setText("")
        self.save_qr_button.setEnabled(False)
        self.poll_status_button.setEnabled(False)

        subject = self.qr_subject_lineedit.text().strip()
        amount = self.qr_amount_lineedit.text().strip()
        out_trade_no = self.qr_trade_lineedit.text().strip()
        timeout = self.qr_timeout_combo.currentText()

        if not subject:
            InfoBar.warning(title="警告", content="请输入商品名称",
                orient=Qt.Orientation.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=3000, parent=self)
            return

        if not amount:
            InfoBar.warning(title="警告", content="请输入支付金额",
                orient=Qt.Orientation.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=3000, parent=self)
            return

        if not out_trade_no:
            out_trade_no = datetime.now().strftime("%Y%m%d%H%M%S") + str(uuid.uuid4().int)[:6]

        self.create_qr_button.setEnabled(False)
        self.qr_status_label.setText("正在生成二维码...")
        self.qr_trade_no_label.setText(f"订单号: {out_trade_no}")
        self._log(f"创建扫码支付订单: {out_trade_no}, 金额: {amount}, 商品: {subject}")

        self.current_qr_trade_no = out_trade_no
        self.precreate_thread = PrecreateThread(
            self.alipay_client, out_trade_no, amount, subject, timeout
        )
        self.precreate_thread.result_ready.connect(self._on_precreate_result)
        self.precreate_thread.error_occurred.connect(self._on_precreate_error)
        self.precreate_thread.start()

    def _on_precreate_result(self, success, qr_code, out_trade_no, qimage):
        # 忽略旧线程的回调
        if out_trade_no != self.current_qr_trade_no:
            return
        self.create_qr_button.setEnabled(True)
        if success and qr_code:
            self.current_qr_code = qr_code
            self._log(f"二维码链接获取成功: {qr_code}")
            # 使用线程中生成的二维码图片
            if qimage:
                pixmap = QPixmap.fromImage(qimage)
                self.qr_code_label.setPixmap(pixmap.scaled(200, 200, Qt.AspectRatioMode.KeepAspectRatio,
                                                             Qt.TransformationMode.SmoothTransformation))
            self.qr_status_label.setText("等待扫码支付...")
            self.qr_trade_no_label.setText(f"订单号: {out_trade_no}")
            self.save_qr_button.setEnabled(True)
            self.poll_status_button.setEnabled(True)

            InfoBar.success(title="二维码已生成", content="请使用支付宝扫码支付",
                orient=Qt.Orientation.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=3000, parent=self)

            # 自动发送订单号到设备 (CMD 0x03)
            if self.serial_conn and self.serial_conn.is_open and out_trade_no:
                trade_data = out_trade_no.encode('utf-8')
                frame = self._build_frame(0x03, trade_data)
                self.serial_conn.write(frame)
                self._log(f"已发送订单号到设备: {out_trade_no}")

            # 自动发送二维码到串口
            self._send_qr_to_device()

            # 自动开始轮询
            self._start_poll()
        else:
            self.qr_status_label.setText("二维码生成失败")
            InfoBar.error(title="失败", content="未获取到二维码链接",
                orient=Qt.Orientation.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=3000, parent=self)

    def _on_precreate_error(self, error):
        # 忽略旧线程的回调（precreate_thread已变更说明是新请求）
        if self.precreate_thread and self.sender() != self.precreate_thread:
            return
        self.create_qr_button.setEnabled(True)
        self.qr_status_label.setText("生成失败")
        self._log(f"扫码支付创建失败: {error}")
        InfoBar.error(title="创建失败", content=error,
            orient=Qt.Orientation.Horizontal, isClosable=True,
            position=InfoBarPosition.TOP, duration=3000, parent=self)

    def _start_poll(self):
        if not self.alipay_client or not self.current_qr_trade_no:
            return
        # 停止之前的轮询（不阻塞等待）
        if self.poll_thread and self.poll_thread.isRunning():
            self.poll_thread.stop()

        self.poll_status_button.setEnabled(False)
        self.qr_status_label.setText("轮询支付状态中...")
        self._log(f"开始轮询订单: {self.current_qr_trade_no}")

        self.poll_thread = PollTradeThread(
            self.alipay_client, self.current_qr_trade_no, max_times=100, interval=3
        )
        self.poll_thread.trade_status.connect(self._on_poll_status)
        self.poll_thread.error_occurred.connect(self._on_poll_error)
        self.poll_thread.start()

    def _on_poll_status(self, status, trade_no):
        # 忽略旧轮询线程的回调
        if trade_no != self.current_qr_trade_no:
            return
        self.poll_status_button.setEnabled(True)
        # 自动发送支付状态到设备
        self._send_payment_status_to_device(status)
        if status == "TRADE_SUCCESS":
            self.qr_status_label.setText("支付成功!")
            self.qr_status_label.setStyleSheet("color: #10b981; font-size: 16px;")
            self._log(f"订单 {trade_no} 支付成功!")
            InfoBar.success(title="支付成功", content=f"订单 {trade_no} 已完成支付",
                orient=Qt.Orientation.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=5000, parent=self)
        elif status == "TRADE_FINISHED":
            self.qr_status_label.setText("交易已完成")
            self.qr_status_label.setStyleSheet("color: #10b981; font-size: 16px;")
            self._log(f"订单 {trade_no} 交易已完成")
        elif status == "TRADE_CLOSED":
            self.qr_status_label.setText("交易已关闭")
            self.qr_status_label.setStyleSheet("color: #ef4444; font-size: 16px;")
            self._log(f"订单 {trade_no} 交易已关闭")
        elif status == "WAIT_TIMEOUT":
            self.qr_status_label.setText("等待超时，请重新生成")
            self.qr_status_label.setStyleSheet("color: #f59e0b; font-size: 16px;")
            self._log(f"订单 {trade_no} 轮询超时")

    def _on_poll_error(self, error):
        self.poll_status_button.setEnabled(True)
        self.qr_status_label.setText("查询失败，请重试")
        self.qr_status_label.setStyleSheet("color: #ef4444; font-size: 16px;")
        self._log(f"轮询异常终止: {error}")

    def _save_qr_code(self):
        pixmap = self.qr_code_label.pixmap()
        if not pixmap:
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存二维码", "qrcode_payment.png", "PNG图片 (*.png);;所有文件 (*)"
        )
        if file_path:
            if pixmap.save(file_path):
                self._log(f"二维码已保存: {file_path}")
                InfoBar.success(title="保存成功", content=f"二维码已保存到 {file_path}",
                    orient=Qt.Orientation.Horizontal, isClosable=True,
                    position=InfoBarPosition.TOP, duration=3000, parent=self)
            else:
                InfoBar.error(title="保存失败", content="无法保存图片",
                    orient=Qt.Orientation.Horizontal, isClosable=True,
                    position=InfoBarPosition.TOP, duration=3000, parent=self)

    def _create_payment(self):
        if not self.alipay_client:
            InfoBar.warning(
                title="警告",
                content="请先初始化客户端",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        subject = self.subject_lineedit.text().strip()
        amount = self.amount_lineedit.text().strip()
        out_trade_no = self.out_trade_lineedit.text().strip()
        return_url = self.return_url_lineedit.text().strip()

        if not subject:
            InfoBar.warning(
                title="警告",
                content="请输入订单标题",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        if not amount:
            InfoBar.warning(
                title="警告",
                content="请输入订单金额",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        if not out_trade_no:
            out_trade_no = datetime.now().strftime("%Y%m%d%H%M%S") + str(uuid.uuid4().int)[:6]

        try:
            order_string = self.alipay_client.api_alipay_trade_page_pay(
                out_trade_no=out_trade_no,
                total_amount=amount,
                subject=subject,
                return_url=return_url if return_url else None,
            )

            gateway = self.gateway_lineedit.text().strip()
            pay_url = f"{gateway}?{order_string}"

            self._log(f"支付订单创建成功")
            self._log(f"订单号: {out_trade_no}")
            self._log(f"金额: {amount} 元")
            self._log(f"标题: {subject}")
            self._log(f"支付链接: {pay_url}")

            QDesktopServices.openUrl(QUrl(pay_url))

            InfoBar.success(
                title="订单创建成功",
                content=f"订单号: {out_trade_no}，已打开支付页面",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=5000,
                parent=self,
            )
        except Exception as e:
            self._log(f"创建支付订单失败: {str(e)}")
            InfoBar.error(
                title="创建失败",
                content=str(e),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )

    def _query_trade(self):
        if not self.alipay_client:
            InfoBar.warning(
                title="警告",
                content="请先初始化客户端",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        out_trade_no = self.query_trade_lineedit.text().strip()
        if not out_trade_no:
            InfoBar.warning(
                title="警告",
                content="请输入订单号",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        self.query_button.setEnabled(False)
        self._log(f"查询订单: {out_trade_no}")

        self.query_thread = TradeQueryThread(self.alipay_client, out_trade_no)
        self.query_thread.result_ready.connect(self._on_query_result)
        self.query_thread.error_occurred.connect(self._on_query_error)
        self.query_thread.start()

    def _on_query_result(self, success, result):
        self.query_button.setEnabled(True)
        self._log(f"查询结果:\n{result}")
        if success:
            InfoBar.success(
                title="查询成功",
                content="订单查询完成",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )

    def _on_query_error(self, error):
        self.query_button.setEnabled(True)
        self._log(f"查询失败: {error}")
        InfoBar.error(
            title="查询失败",
            content=error,
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=3000,
            parent=self,
        )

    def _refund_trade(self):
        if not self.alipay_client:
            InfoBar.warning(
                title="警告",
                content="请先初始化客户端",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        out_trade_no = self.refund_trade_lineedit.text().strip()
        refund_amount = self.refund_amount_lineedit.text().strip()
        refund_reason = self.refund_reason_lineedit.text().strip()

        if not out_trade_no:
            InfoBar.warning(
                title="警告",
                content="请输入订单号",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        if not refund_amount:
            InfoBar.warning(
                title="警告",
                content="请输入退款金额",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        self.refund_button.setEnabled(False)
        self._log(f"退款请求: 订单号={out_trade_no}, 金额={refund_amount}")

        self.refund_thread = TradeRefundThread(
            self.alipay_client, out_trade_no, refund_amount,
            refund_reason if refund_reason else None
        )
        self.refund_thread.result_ready.connect(self._on_refund_result)
        self.refund_thread.error_occurred.connect(self._on_refund_error)
        self.refund_thread.start()

    def _on_refund_result(self, success, result):
        self.refund_button.setEnabled(True)
        self._log(f"退款结果:\n{result}")
        if success:
            InfoBar.success(
                title="退款成功",
                content="退款操作完成",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )

    def _on_refund_error(self, error):
        self.refund_button.setEnabled(True)
        self._log(f"退款失败: {error}")
        InfoBar.error(
            title="退款失败",
            content=error,
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=3000,
            parent=self,
        )

    def _close_trade(self):
        if not self.alipay_client:
            InfoBar.warning(
                title="警告",
                content="请先初始化客户端",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        out_trade_no = self.close_trade_lineedit.text().strip()
        if not out_trade_no:
            InfoBar.warning(
                title="警告",
                content="请输入订单号",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        self.close_button.setEnabled(False)
        self._log(f"关闭订单: {out_trade_no}")

        self.close_thread = TradeCloseThread(self.alipay_client, out_trade_no)
        self.close_thread.result_ready.connect(self._on_close_result)
        self.close_thread.error_occurred.connect(self._on_close_error)
        self.close_thread.start()

    def _on_close_result(self, success, result):
        self.close_button.setEnabled(True)
        self._log(f"关闭结果:\n{result}")
        if success:
            InfoBar.success(
                title="关闭成功",
                content="订单已关闭",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )

    def _on_close_error(self, error):
        self.close_button.setEnabled(True)
        self._log(f"关闭失败: {error}")
        InfoBar.error(
            title="关闭失败",
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
    w = AlipaySandbox_Widget()
    w.show()
    sys.exit(app.exec())
