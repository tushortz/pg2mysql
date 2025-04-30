# pg2mysql
Converts postgres dumpfile to mysql inserts and update database


> **Note:** It works for most basic stuff and outputs sql queries for the failed inserts into a `temp` folder.

## How to use

Run command for help
```sh
python pg2mysql.py --help
```

## How to run

```sh
python pg2mysql.py -d <output_database_url> -p <postgres_dump.sql> -e <optional_path_to_mysql_executable>
```

> **Note**: Database url must be in the format `mysql://username:password@host/dbname`
