#!/usr/bin/env sh
# Builds classes3.dex (the day/night module) from src/.
# Needs: JDK 11+ and Android build-tools (d8) + platform android.jar.
# Defaults point at the copies in ../work/tools; override with env vars.
set -eu
cd "$(dirname "$0")"
TOOLS="${TOOLS:-../work/tools}"
JAVA_HOME="${JAVA_HOME:-$TOOLS/jdk-17.0.13+11}"; export JAVA_HOME
ANDROID_JAR="${ANDROID_JAR:-$TOOLS/android-34/android.jar}"
LAMBDA_STUBS="${LAMBDA_STUBS:-$TOOLS/build-tools-34/core-lambda-stubs.jar}"
D8="${D8:-$TOOLS/build-tools-34/d8.bat}"
[ -f "$D8" ] || D8="$TOOLS/build-tools-34/d8"

rm -rf build && mkdir -p build/classes build/stubs build/dex
# Stubs are compiled separately so they can't end up in the dex.
"$JAVA_HOME/bin/javac" -source 8 -target 8 -bootclasspath "$ANDROID_JAR;$LAMBDA_STUBS" -Xlint:-options \
    -d build/stubs $(find stubs -name '*.java')
"$JAVA_HOME/bin/javac" -source 8 -target 8 -bootclasspath "$ANDROID_JAR;$LAMBDA_STUBS" -Xlint:-options -Xlint:all \
    -classpath build/stubs -d build/classes $(find src -name '*.java')
"$D8" --release --min-api 26 --lib "$ANDROID_JAR" --classpath build/stubs \
    --output build/dex $(find build/classes -name '*.class')
mv build/dex/classes.dex build/classes3.dex
echo "built build/classes3.dex ($(wc -c < build/classes3.dex) bytes)"
