Set-Location "D:\Knowledge_Map\data_to_db"
poetry run python process_pmc_manual.py *> "D:\Knowledge_Map\data_to_db\logs\pmc_manual_run.log"
