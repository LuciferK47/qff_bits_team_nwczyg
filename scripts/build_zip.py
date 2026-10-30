"""python scripts/build_zip.py  ->  dist/<team_name>.zip (team name from configs/team.yaml)"""
from qtrust import package

path, info = package.build()
print(path, info)
if info["missing_required"] or info["forbidden_present"]:
    raise SystemExit(f"archive incomplete or contaminated: {info}")
