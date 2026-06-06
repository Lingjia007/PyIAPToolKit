# coding:utf-8
import sys
import os
import json
import uuid
from datetime import datetime
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFileDialog,
    QGroupBox,
    QGridLayout,
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
    SpinBox,
    TextEdit,
    HyperlinkButton,
    ScrollArea,
)

from settings.config import cfg

try:
    from alipay import AliPay
    ALIPAY_AVAILABLE = True
except ImportError:
    ALIPAY_AVAILABLE = False


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

        self._init_config_ui()
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
            copy_btn.setFixedWidth(60)
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
            copy_btn.setFixedWidth(60)
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
        bg_color = "#202020" if is_dark else "#f5f5f5"

        widgets_to_update = [
            getattr(self, 'config_group', None),
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
