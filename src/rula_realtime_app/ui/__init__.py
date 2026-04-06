"""
UI 封裝匯出模組。

集中匯出各主要視窗類別，讓外部程式可由單一入口匯入：
- MainWindow：即時分析視窗
- LauncherWindow：模式選擇首頁
- UploadWindow：影片上傳分析視窗
- HistoryWindow：歷史紀錄清單視窗
- ResultWindow：分析結果視窗
"""

from .realtime_window import MainWindow
from .launcher_window import LauncherWindow
from .upload_window   import UploadWindow
from .history_window  import HistoryWindow
from .result_window   import ResultWindow

__all__ = [
    'MainWindow',
    'LauncherWindow',
    'UploadWindow',
    'HistoryWindow',
    'ResultWindow',
]
