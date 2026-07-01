@echo off
REM NewsRadar 每日新闻情报管线 - 定时任务入口
REM 由 Windows Task Scheduler 每天早上 06:00 调用

setlocal

set PYTHONIOENCODING=utf-8
set PROJECT_DIR=D:\Python_Program\news_program

echo ========================================
echo  NewsRadar Daily Pipeline
echo  %date% %time%
echo ========================================

cd /d "%PROJECT_DIR%"

REM 使用 managed Python 运行管线
C:\Users\Vasily_A_K\.workbuddy\binaries\python\versions\3.13.12\python.exe run_news_pipeline.py

echo ========================================
echo  Pipeline finished at %time%
echo ========================================
