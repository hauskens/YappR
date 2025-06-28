#!/usr/bin/env sh

# Create directories
mkdir -p app/static/js
mkdir -p app/static/css/fonts

# Copy JavaScript files
cp node_modules/htmx.org/dist/htmx.min.js app/static/js/
cp node_modules/socket.io-client/dist/socket.io.min.js app/static/js/
cp node_modules/chart.js/dist/chart.umd.js app/static/js/
cp node_modules/chartjs-plugin-zoom/dist/chartjs-plugin-zoom.min.js app/static/js/
cp node_modules/github-buttons/dist/buttons.js app/static/js/
cp node_modules/vanilla-cookieconsent/dist/cookieconsent.umd.js app/static/js/

echo "✓ Copied all JavaScript dependencies"

cp node_modules/vanilla-cookieconsent/dist/cookieconsent.css app/static/css/
cp node_modules/bootstrap-icons/font/bootstrap-icons.css app/static/css/
cp -r node_modules/bootstrap-icons/font/fonts/* app/static/css/fonts/ 
echo "✓ Copied Bootstrap Icons"
