import pandas as pd
import numpy as np

data = pd.read_csv("Scenario FAQ - With Service - end of 09031405 (v3).csv")

# final_data = pd.DataFrame(columns=["question_and_answer", "category", "sub_category"])
final_data = pd.DataFrame(columns=["question_and_answer", "category"])

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

final_data.to_csv("/nvme/Chatbot/faq/Scenario FAQ - With Service - end of 09031405 (v3)_Ready2Chunk.csv")