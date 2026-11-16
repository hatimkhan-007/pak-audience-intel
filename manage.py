#!/usr/bin/env python3
"""Command line for the Campaign Intelligence Engine.

  python manage.py setup            build DB with simulated data + run analysis
  python manage.py run              start the web app  (http://127.0.0.1:5000)
  python manage.py analyze          re-run clustering / anomalies / recommendations
  python manage.py import-youtube [--csv path]   add YouTube comments from the sentiment analyzer
  python manage.py import --posts posts.csv --comments comments.csv --source "My scrape" --url https://...
"""
import argparse, sys
from campaign_engine import config, pipeline, database as db


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("setup"); s.add_argument("--posts", type=int, default=config.N_POSTS); s.add_argument("--seed", type=int, default=config.SEED)
    r = sub.add_parser("run"); r.add_argument("--host", default="127.0.0.1"); r.add_argument("--port", type=int, default=5000); r.add_argument("--debug", action="store_true")
    sub.add_parser("analyze")
    y = sub.add_parser("import-youtube", help="load the YouTube Comment Sentiment Analyzer CSV (classified_comments.csv)")
    y.add_argument("--csv", default=str(config.YOUTUBE_CSV)); y.add_argument("--reanalyze", action="store_true", help="also refresh clustering (not needed: YouTube is excluded from it)")
    i = sub.add_parser("import", help="append REAL (observed) data from CSV files")
    i.add_argument("--posts", required=True); i.add_argument("--comments", required=True)
    i.add_argument("--source", required=True); i.add_argument("--url", default=None)
    i.add_argument("--collected", default=config.COLLECTION_DATE); i.add_argument("--permission", default="Check platform terms before redistributing")
    a = ap.parse_args()

    if a.cmd == "setup":
        print("Building database ..."); print(pipeline.build(a.posts, a.seed)); print("Done. Start the app with: python manage.py run")
    elif a.cmd == "run":
        from campaign_engine.webapp import create_app
        if not config.DB_PATH.exists():
            print("No database yet - building one first ..."); pipeline.build()
        create_app().run(host=a.host, port=a.port, debug=a.debug)
    elif a.cmd == "analyze":
        conn = db.connect(); print(pipeline.run_analysis(conn)); conn.close()
    elif a.cmd == "import-youtube":
        from campaign_engine.importer import import_youtube
        print(import_youtube(a.csv))
    elif a.cmd == "import":
        from campaign_engine.importer import import_csv
        print(import_csv(a.posts, a.comments, a.source, a.url, a.collected, a.permission))


if __name__ == "__main__":
    sys.exit(main())
