import argparse
import itertools
import os
import re
import shutil
import subprocess

import dj_database_url


def extract_pg_contents(pg_dump_file: str) -> list[str]:
    pg_contents = []
    with open(pg_dump_file, "r", encoding="utf-8", errors="ignore") as f:
        ignore = True
        for line in f:
            if line.startswith("COPY public."):
                ignore = False

            if ignore:
                continue

            line = line.replace("\n", ">>>")
            pg_contents.append(line)

    return pg_contents


def transform_pg_to_mysql(contents: list[str]) -> list[str]:
    paths = []
    data = "".join(contents)
    content = re.findall(r"COPY public\.(.*?) (.*?) FROM stdin;>>>(.*?)\\\.", data)
    for i, line in enumerate(content, 1):
        table_name, fields, values = line
        fields = re.findall(r"\w+", fields)
        first_field = fields[0] if fields else "id"

        fields = ", ".join([f"`{field}`" for field in fields])
        fields = f"({fields})"

        values = values.replace("\\N", "")
        values = re.sub(r"\bt\b", "1", values)
        values = re.sub(r"\bf\b", "0", values)

        # if re.search(r"<[a-zA-Z]+>.*?</[a-zA-Z]+>", values):
        #     values = escape(values)

        values = values.replace(">>>", "\n")

        values = values.lstrip().split("\n")

        it = iter(values)
        part_index = 1
        while chunk := list(itertools.islice(it, 10_000)):
            values_chunk = []
            for value in chunk:
                if value:
                    value = str(tuple(value.split("\t"))) + ","
                    values_chunk.append(value)

            values_chunk = "\n".join(values_chunk).strip(",")

            query = f"SET FOREIGN_KEY_CHECKS=0;\n\nINSERT INTO `{table_name}` {fields} VALUES \n{values_chunk} \n\nON DUPLICATE KEY UPDATE `{first_field}`=`{first_field}`;\n"

            if not values_chunk:
                print(f"- Skipping {table_name} as it has no data.")
                continue

            path = f"temp/{table_name}_{part_index}.sql"
            with open(path, "w", encoding="utf-8") as f:
                f.write(query)

            print(f"+ {i}. query for {table_name} ({part_index}) created.")
            paths.append(path)
            part_index += 1

    return paths


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        "pg2mysql",
        usage="%(prog)s [options]",
        description="PostgreSQL to MySQL migration script.",
    )
    parser.add_argument(
        "-d",
        "--database-url",
        help="Database config url.",
        required=True,
    )
    parser.add_argument(
        "-p",
        "--pgdump-file",
        help="PostgreSQL dump file.",
        required=True,
    )
    parser.add_argument(
        "-r",
        "--resume",
        help="Resume the migration process.",
        required=False,
        default=False,
    )
    parser.add_argument(
        "-e",
        "--mysql-path",
        help="Path to mysql command. default assumes mysql is in PATH.",
        required=False,
        default="mysql",
    )

    args = parser.parse_args()
    db_config = dj_database_url.parse(args.database_url)
    resume = args.resume

    username = db_config["USER"]
    password = db_config["PASSWORD"]
    host = db_config["HOST"]
    port = db_config["PORT"]
    database_name = db_config["NAME"]

    if not resume:
        print("x Removing temp directory...")
        shutil.rmtree("temp", ignore_errors=True)
        os.makedirs("temp", exist_ok=True)

        contents = extract_pg_contents(pg_dump_file=args.pgdump_file)
        file_paths = transform_pg_to_mysql(contents)
    else:
        try:
            file_paths = os.listdir("temp")
            print("x Resuming...")

        except FileNotFoundError:
            file_paths = []
            print("Nothing to resume.")
        file_paths = [f"temp/{file_path}" for file_path in file_paths]

    for file_path in file_paths:
        print(f"x Executing {file_path}...")

        cmd = subprocess.run(
            [
                args.mysql_path,  # Path to mysql executable
                f"--user={username}",
                f"--password={password}",
                f"--host={host}",
                f"--port={port}",
                "--default-character-set=utf8mb4",
                "--compress",
                "--max-allowed-packet=1G",
                f"--database={database_name}",
                "<",
                file_path,
            ],
            check=False,
            shell=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        output = cmd.stderr or cmd.stdout
        if output:
            print(output)
        else:
            print(f"+ {file_path} executed.")
            os.remove(file_path)
