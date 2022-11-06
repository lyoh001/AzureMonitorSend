import base64
import logging
import os
import tempfile

import azure.functions as func
import matplotlib.pyplot as plt
import pandas as pd
import requests
from azure.cosmosdb.table.tableservice import TableService
from pandas_profiling import ProfileReport


def main(mytimer: func.TimerRequest) -> None:
    account_keys = os.environ["AZUREMONITOREVENTSTRGE_CONNECTION"].split(";")
    table_service = TableService(
        account_name=account_keys[1][12:], account_key=account_keys[2][11:]
    )
    graph_base64_messages = dict()
    for table in table_service.list_tables():
        df = pd.DataFrame(table_service.query_entities(table.name).items)
        with tempfile.TemporaryDirectory() as tempdir_path:
            report_path = os.path.join(tempdir_path, "report.html")
            ProfileReport(pd.DataFrame(df), minimal=True, lazy=True, dark_mode=True, pool_size=1).to_file(report_path)
            with open(report_path, "r") as file_reader:
                graph_base64_messages["report"] = file_reader.read()

        plt.style.use("bmh")
        plt.figure(figsize=(15, 5))
        ax = plt.subplot(1, 2, 1)
        bars = ax.bar(
            (sub_df := df.groupby("SubscriptionName").count()).index,
            sub_df["PartitionKey"],
            alpha=0.7,
            color="purple",
            label="No. Alerts",
        )
        for bar in bars:
            height = bar.get_height()
            ax.annotate(
                f"{height} alert(s)",
                xy=(bar.get_x() + bar.get_width() / 2, height),
                xytext=(0, 3),
                textcoords="offset points",
                ha="center",
                va="bottom",
            )
        plt.title("VICGOV Azure Weekly Alerts Generated per Subscription")
        plt.xlabel("Subscription Names")
        plt.xticks(rotation="0")
        plt.ylabel("Total No. of Alerts")
        plt.legend(loc="lower right")
        plt.tight_layout()

        with tempfile.TemporaryDirectory() as tempdir_path:
            bar_graph_path = os.path.join(tempdir_path, f"{table.name}_bar_graph.jpg")
            plt.savefig(bar_graph_path)
            with open(bar_graph_path, "rb") as file_reader:
                message_bytes = file_reader.read()
                base64_bytes = base64.b64encode(message_bytes)
                graph_base64_messages[f"{table.name}_bar_graph"] = base64_bytes.decode(
                    "ascii"
                )

        plt.figure(figsize=(15, 5))
        ax = plt.subplot(1, 2, 1)
        ax.barh(
            [
                f"{(upn := user.split('@'))[0]}\n@{upn[1]}"
                if "@" in user
                else "\n".join(c for c in user.split())
                for user in df.groupby("PartitionKey").count().index
            ],
            df.groupby("PartitionKey").count()["RowKey"],
            alpha=0.7,
            color="navy",
            label="No. Alerts",
        )
        plt.title("VICGOV Azure Weekly Alerts Generated per UPN")
        plt.xlabel("Total No. of Alerts")
        plt.xticks(rotation="0")
        plt.ylabel("User Principal Names")
        plt.legend(loc="lower right")
        plt.tight_layout()

        with tempfile.TemporaryDirectory() as tempdir_path:
            hbar_graph_path = os.path.join(tempdir_path, f"{table.name}_hbar_graph.jpg")
            plt.savefig(hbar_graph_path)
            with open(hbar_graph_path, "rb") as file_reader:
                message_bytes = file_reader.read()
                base64_bytes = base64.b64encode(message_bytes)
                graph_base64_messages[f"{table.name}_hbar_graph"] = base64_bytes.decode(
                    "ascii"
                )

        plt.figure(figsize=(17, 10))
        ax = plt.subplot(1, 2, 1)
        ax.pie(
            (upn_df := df.groupby("PartitionKey").count()["OperationName"]),
            labels=[
                f"{(upn := user.split('@'))[0]}\n@{upn[1]}" if "@" in user else user
                for user in upn_df.index
            ],
            autopct="%1.1f%%",
            shadow=False,
            startangle=90,
            textprops={"fontsize": 7},
        )
        plt.title("VICGOV Azure Weekly Alerts Generated per UPN")
        plt.xlabel("")
        plt.xticks(rotation="90")
        plt.ylabel("")
        plt.legend(loc="lower left", labels=upn_df.index)
        plt.tight_layout()

        with tempfile.TemporaryDirectory() as tempdir_path:
            pie_graph_path1 = os.path.join(tempdir_path, f"{table.name}_pie_graph1.jpg")
            plt.savefig(pie_graph_path1)
            with open(pie_graph_path1, "rb") as file_reader:
                message_bytes = file_reader.read()
                base64_bytes = base64.b64encode(message_bytes)
                graph_base64_messages[f"{table.name}_pie_graph1"] = base64_bytes.decode(
                    "ascii"
                )

    try:
        logging.info(
            (
                response := requests.post(
                    url=os.environ["LOGICAPP_URI"],
                    json=graph_base64_messages,
                )
            )
        )

        if f"{response.status_code}".startswith("2"):
            logging.info("Deleting table entities.")
            for table in table_service.list_tables():
                entities = table_service.query_entities(table_name=table.name)
                [
                    table_service.delete_entity(
                        table_name=table.name,
                        partition_key=entity["PartitionKey"],
                        row_key=entity["RowKey"],
                    )
                    for entity in entities.items
                ]

    except requests.exceptions.RequestException as e:
        raise SystemExit(e)
