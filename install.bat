@echo off
:: HAR vs JMeter Listener — Install Script (Windows)
:: Run this after building the JAR with: mvn clean package

setlocal

set JAR=target\har-jmeter-listener-1.0.0-plugin.jar

if not exist "%JAR%" (
    echo ERROR: JAR not found. Run "mvn clean package" first.
    pause
    exit /b 1
)

:: Try to find JMeter
if defined JMETER_HOME (
    set JMETER_LIB=%JMETER_HOME%\lib\ext
) else (
    set /p JMETER_HOME=Enter your JMeter home path (e.g. C:\apache-jmeter-5.6): 
    set JMETER_LIB=%JMETER_HOME%\lib\ext
)

if not exist "%JMETER_LIB%" (
    echo ERROR: JMeter lib\ext folder not found at %JMETER_LIB%
    pause
    exit /b 1
)

copy /Y "%JAR%" "%JMETER_LIB%\"
echo.
echo ✓ Plugin installed to %JMETER_LIB%
echo ✓ Restart JMeter and look for "HAR vs JMeter Listener" under Listeners
echo.
pause
