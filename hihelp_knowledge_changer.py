import pandas as pd
import numpy as np

import os
from dotenv import load_dotenv

# Load variables from .env into os.environ
load_dotenv()


# data = pd.read_csv("/nvme/Chatbot/faq/FAQ - end of 23031405 (v2).csv")
# data_insertion_chunks_directory = "/nvme/Chatbot/faq/data_insertion_chunks"

data = pd.read_csv(os.getenv("KNOWLEDGE_BASE_CSV"))
data_insertion_chunks_directory = os.getenv("DATA_INSERTION_DIRECTORY")

chunk_dir_name = "General_FAQ"
chunks_directory = data_insertion_chunks_directory +  "/CHUNKS" + f"/{chunk_dir_name}"



final_data = pd.DataFrame(columns=["question_and_answer", "category", "sub_category"])
# final_data = pd.DataFrame(columns=["question_and_answer", "category"])

for i in range(0, len(data)):
    user_question = data.iloc[i]['سوال استاندارد'].replace("\u200c", " ")
    # print(user_question)
    print(i)
    category = data.iloc[i]['موضوع اصلی'].replace("\u200c", " ")
    if type(data.iloc[i]['کلید کنترل تجمیع']) == str:
        sub_category = data.iloc[i]['کلید کنترل تجمیع'].replace("\u200c", " ")
    else:
        sub_category = ""
    intended_question = data.iloc[i]['سوال شفاف‌سازی شده'].replace("\u200c", " ")

    answer = (data.iloc[i]['پاسخ']).replace("\u200c", " ")
    # print(answers)

    question_and_answer = f"question : {intended_question}\nanswer : {answer}"

    new_row = pd.DataFrame({"question_and_answer": [question_and_answer], "category": [category], "sub_category": [sub_category]})
    # new_row = pd.DataFrame({"question_and_answer": [question_and_answer], "category": [category]})

    final_data = pd.concat([final_data, new_row], ignore_index=True)


for i in range(0,len(final_data)):
    user_question_and_answer = final_data.iloc[i]["question_and_answer"].replace("\u200c", " ")
    category = final_data.iloc[i]["category"].replace("\u200c", " ")

    if type(final_data.iloc[i]['sub_category']) == str:
        sub_category = final_data.iloc[i]['sub_category'].replace("\u200c", " ")
        data = f"{user_question_and_answer}\nquestion category : {category.replace("\n", " ")}. sub_category : {sub_category.replace("\n", " ")}"

    else:
        sub_category = ""
        data = f"{user_question_and_answer}question category : {category.replace("\n", " ")}."

    # data = f"{user_question_and_answer}\nquestion category : {category.replace("\n", " ")}"

    with open(f"{chunks_directory}/{chunk_dir_name}_{i}.txt", "w", newline="", encoding="utf8") as file:
        file.write(data)

final_data.to_csv(data_insertion_chunks_directory + f"/DOCUMENTS/{chunk_dir_name}.csv")