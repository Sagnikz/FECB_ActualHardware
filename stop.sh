echo "Stopping all GMRT FECB Tango services..."

pkill -f "tango.databaseds.database" 2>/dev/null && echo "Tango DB stopped"
pkill -f "FECB.py"                   2>/dev/null && echo "FECB Server stopped"
pkill -f "FECB_Proxy.py"             2>/dev/null && echo "Proxy stopped"
pkill -f "FECB_Archiver.py"          2>/dev/null && echo "Archiver stopped"
pkill -f "app.py"                    2>/dev/null && echo "Web GUI stopped"

rm -f /tmp/gmrt_v1_pids.txt
echo ""
echo "Done. To also stop hardware client run:"
echo "  cd /home/fe-dell/FECB_Lab && ./stop_deviceclient.sh"
