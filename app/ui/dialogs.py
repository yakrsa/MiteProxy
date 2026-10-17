"""中文标准按钮的消息/确认框 + QDialogButtonBox 中文化（仅中文模式）。

Qt 的 QMessageBox / QDialogButtonBox 标准按钮默认英文（OK/Cancel/Yes/No），
而 PySide6 不带 qt_zh_CN 翻译，界面里就会冒出英文按钮。统一在这里收口：

- `information / warning / critical / question`：等价于 QMessageBox 的静态
  方法，但内部创建实例、把标准按钮改成中文再 exec；`question` 的返回值仍是
  `QMessageBox.StandardButton`（调用方的 `== QMessageBox.StandardButton.Yes`
  判断不受影响——exec() 返回的是 int，这里转回 enum 避免 enum/int 比较踩坑）。
- `cn_button_box`：把一个 QDialogButtonBox 的标准按钮中文化；**只替换还是
  Qt 英文默认值的按钮**，已自定义中文文本的（如"导入所选"）保留不动。
"""

from __future__ import annotations

from PySide6.QtWidgets import QDialogButtonBox, QMessageBox, QWidget

#: 标准按钮 → 中文文案
_CN = {
    QMessageBox.StandardButton.Ok: "确定",
    QMessageBox.StandardButton.Cancel: "取消",
    QMessageBox.StandardButton.Yes: "是",
    QMessageBox.StandardButton.No: "否",
    QMessageBox.StandardButton.Close: "关闭",
    QMessageBox.StandardButton.Apply: "应用",
    QMessageBox.StandardButton.Reset: "重置",
    QMessageBox.StandardButton.Save: "保存",
    QMessageBox.StandardButton.Discard: "放弃",
    QMessageBox.StandardButton.Abort: "中止",
    QMessageBox.StandardButton.Retry: "重试",
    QMessageBox.StandardButton.Ignore: "忽略",
    QMessageBox.StandardButton.Help: "帮助",
    QMessageBox.StandardButton.Open: "打开",
}

#: 各标准按钮的 Qt 英文默认文本（仅当按钮文本仍等于它才中文化，避免覆盖自定义）
_EN = {
    QMessageBox.StandardButton.Ok: "OK",
    QMessageBox.StandardButton.Cancel: "Cancel",
    QMessageBox.StandardButton.Yes: "Yes",
    QMessageBox.StandardButton.No: "No",
    QMessageBox.StandardButton.Close: "Close",
    QMessageBox.StandardButton.Apply: "Apply",
    QMessageBox.StandardButton.Reset: "Reset",
    QMessageBox.StandardButton.Save: "Save",
    QMessageBox.StandardButton.Discard: "Discard",
    QMessageBox.StandardButton.Abort: "Abort",
    QMessageBox.StandardButton.Retry: "Retry",
    QMessageBox.StandardButton.Ignore: "Ignore",
    QMessageBox.StandardButton.Help: "Help",
    QMessageBox.StandardButton.Open: "Open",
}


def _cn_std_buttons(box) -> None:
    """中文模式下把消息框/按钮框里还是英文默认文本的标准按钮改成中文。

    英文模式下不碰：Qt 标准按钮默认就是英文（OK/Cancel…），装了英文翻译器后
    正好保持英文，无需替换。
    """
    from app.i18n import current_language

    if current_language() != "zh_CN":
        return
    for btn in box.buttons():
        std = box.standardButton(btn)
        if std in _CN and btn.text() == _EN.get(std, ""):
            btn.setText(_CN[std])


def _mk(parent, icon, title, text, buttons, default=None) -> QMessageBox:
    box = QMessageBox(parent)
    box.setIcon(icon)
    box.setWindowTitle(title)
    box.setText(text)
    box.setStandardButtons(buttons)
    if default is not None:
        box.setDefaultButton(default)
    _cn_std_buttons(box)
    return box


def information(parent, title, text, buttons=QMessageBox.StandardButton.Ok):
    return _mk(parent, QMessageBox.Icon.Information, title, text, buttons).exec()


def warning(parent, title, text, buttons=QMessageBox.StandardButton.Ok):
    return _mk(parent, QMessageBox.Icon.Warning, title, text, buttons).exec()


def critical(parent, title, text, buttons=QMessageBox.StandardButton.Ok):
    return _mk(parent, QMessageBox.Icon.Critical, title, text, buttons).exec()


def question(parent, title, text,
             buttons=(QMessageBox.StandardButton.Yes
                      | QMessageBox.StandardButton.No),
             default=QMessageBox.StandardButton.No):
    box = _mk(parent, QMessageBox.Icon.Question, title, text, buttons, default)
    box.exec()
    clicked = box.clickedButton()
    if clicked is not None:
        return box.standardButton(clicked)
    return QMessageBox.StandardButton.Cancel


def cn_button_box(buttons: QDialogButtonBox) -> None:
    """QDialogButtonBox 中文化：只替换英文默认按钮，自定义中文文本保留。"""
    _cn_std_buttons(buttons)
