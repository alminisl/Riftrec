#!/bin/bash
# Monitor bulk_scrape_v3.py and restart if it's not running (Windows-compatible)
SCRAPER_DIR="F:/Projects/riftrec/scraper"
LOG="$SCRAPER_DIR/monitor.log"
LOCKFILE="$SCRAPER_DIR/scraper.lock"

echo "[$(date)] Monitor started" >> "$LOG"

while true; do
    # Check if any python process is running bulk_scrape_v3
    # Use wmic to check command lines on Windows
    SCRAPER_COUNT=$(wmic process where "name='python3.13.exe'" get CommandLine 2>/dev/null | grep -c "bulk_scrape_v3")

    if [ "$SCRAPER_COUNT" -eq 0 ]; then
        echo "[$(date)] Scraper not running, restarting..." >> "$LOG"
        cd "$SCRAPER_DIR"
        python bulk_scrape_v3.py --delay 1.5 --workers 1 >> "$SCRAPER_DIR/scraper.log" 2>&1 &
        echo "[$(date)] Scraper restarted" >> "$LOG"
    elif [ "$SCRAPER_COUNT" -gt 1 ]; then
        echo "[$(date)] WARNING: $SCRAPER_COUNT scrapers running! Killing extras..." >> "$LOG"
        # Kill all and restart one
        taskkill //F //IM python3.13.exe > /dev/null 2>&1
        sleep 3
        cd "$SCRAPER_DIR"
        python bulk_scrape_v3.py --delay 1.5 --workers 1 >> "$SCRAPER_DIR/scraper.log" 2>&1 &
        echo "[$(date)] Restarted single scraper" >> "$LOG"
    else
        # Log progress
        if [ -f "$SCRAPER_DIR/data/scrape_progress/progress.json" ]; then
            PROGRESS=$(cat "$SCRAPER_DIR/data/scrape_progress/progress.json" | tr -d '\n')
            echo "[$(date)] OK (1 scraper). $PROGRESS" >> "$LOG"
        fi
        DETAILS=$(ls "$SCRAPER_DIR/data/scrape_progress/deck_details/" 2>/dev/null | wc -l | tr -d ' ')
        echo "[$(date)] Deck details: $DETAILS" >> "$LOG"
    fi
    sleep 300
done
