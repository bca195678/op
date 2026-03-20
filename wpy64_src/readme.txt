--------------------------------------------------------------------------------
Setup WPY (手動)：
--------------------------------------------------------------------------------
git clone下載後，請依照以下步驟手動執行

Step 0. 如需設定 Proxy，請執行以下指令：
            set http_proxy=http://172.19.176.170:3128

Step 1. 依據 version.txt 中的 winpython_filename 欄位，執行對應的安裝檔，例如：
            .\Winpython64-3.x.x.xdot.exe

Step 2. 安裝完成後，將解壓後的資料夾（例如：.\WPy64-3xxxxx\）重新命名為：
            .\wpy64\

Step 3. 啟動 WinPython 命令列環境：
            .\wpy64\scripts\activate.bat

Step 4. [DEPRECATED]   

Step 5. 安裝相依套件（從上層目錄的 requirements.txt）：
            python -m pip install --no-index --find-links=packages/ -r requirements.txt --no-warn-script-location
            註：--no-index --find-links=packages/ 不連線至PyPI下載，指定從本地的packages/資料夾安裝package
                預先連線至PyPI下載packages到本地: python -m pip download -r requirements.txt -d ./packages
            註：--no-warn-script-location 抑制腳本路徑警告訊息

Step 6. 將 .\wpy64\ 整個資料夾複製到產測系統的根目錄下


--------------------------------------------------------------------------------
Setup WPY (自動)：
--------------------------------------------------------------------------------
git clone下載後，請依照以下步驟執行自動安裝

Step 0. 如需設定 Proxy，請執行以下指令：
            set http_proxy=http://172.19.176.170:3128

Step 1.   執行自動安裝腳本：
                .\wpy64_src\setup_wpy.bat

註：自動安裝會執行上述手動步驟 1-6，包括：
    - WinPython 安裝與重新命名
    - 檔案複製與目錄設定
    - 客製化套件建置
    - 相依套件安裝

如果自動安裝失敗，請參考上方手動安裝步驟進行除錯。 
