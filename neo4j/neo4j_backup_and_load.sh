# Команды для создания бэкапа БД Neo4j и его последующая загрузка в новую БД
# https://neo4j.com/docs/operations-manual/current/kubernetes/operations/dump-load/


# Через Docker

## Бэкап (dump)
## Запустив из папки на хосте D:\Данные\knowledge_map_app\ где также на хосте находится папка backups
docker run --rm --volumes-from knowledge_map_neo4j -v D:\Данные\knowledge_map_app\backups:/backups neo4j:5.13.0 bash -c 'bin/neo4j-admin database dump neo4j --to-stdout > /backups/neo4j.dump'

## Импорт или восстановление в другую БД (load)
docker run --rm --volumes-from knowledge_map_neo4j -v D:\Данные\knowledge_map_app\backups:/backups neo4j:5.13.0 /bin/bash -c "bin/neo4j-admin database load --from=/backups/neo4j.dump --database=neo4j --force"



# Не через Docker

# neo4j-admin database load --expand-commands system --from-path=/backups --overwrite-destination=true && neo4j-admin database load --expand-commands neo4j --from-path=/backups --overwrite-destination=true