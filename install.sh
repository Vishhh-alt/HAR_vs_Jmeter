#!/bin/bash
# HAR vs JMeter Listener — Install Script (Mac/Linux)
# Run after: mvn clean package

JAR="target/har-jmeter-listener-1.0.0-plugin.jar"

if [ ! -f "$JAR" ]; then
    echo "ERROR: JAR not found. Run 'mvn clean package' first."
    exit 1
fi

if [ -z "$JMETER_HOME" ]; then
    read -rp "Enter your JMeter home path (e.g. /opt/apache-jmeter-5.6): " JMETER_HOME
fi

LIB_EXT="$JMETER_HOME/lib/ext"

if [ ! -d "$LIB_EXT" ]; then
    echo "ERROR: $LIB_EXT not found. Check your JMETER_HOME."
    exit 1
fi

cp "$JAR" "$LIB_EXT/"
echo ""
echo "✓ Plugin installed to $LIB_EXT"
echo "✓ Restart JMeter and look for 'HAR vs JMeter Listener' under Listeners"
