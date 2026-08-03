import pandas as pd

# from creating_chunking_ready_file_from_general_questions_file import sub_category

# input_data = "/home/hooman/PycharmProjects/HiHelp/final_data_only_original.csv"
input_data = "/nvme/Chatbot/faq/data_insertion_chunks/DOCUMENTS/General_FAQ.csv"
chunks_output_dir = "/nvme/Chatbot/faq/data_insertion_chunks/CHUNKS/General_FAQ"

chunk_dir_name = chunks_output_dir.split("/")[-1]

paraphrased_data = pd.read_csv(input_data)

for i in range(0,len(paraphrased_data)):
    user_question_and_answer = paraphrased_data.iloc[i]["question_and_answer"].replace("\u200c", " ")
    category = paraphrased_data.iloc[i]["category"].replace("\u200c", " ")

    if type(paraphrased_data.iloc[i]['sub_category']) == str:
        sub_category = paraphrased_data.iloc[i]['sub_category'].replace("\u200c", " ")
        data = f"{user_question_and_answer}\nquestion category : {category.replace("\n", " ")}. sub_category : {sub_category.replace("\n", " ")}"

    else:
        sub_category = ""
        data = f"{user_question_and_answer}question category : {category.replace("\n", " ")}."

    # data = f"{user_question_and_answer}\nquestion category : {category.replace("\n", " ")}"

    with open(f"{chunks_output_dir}/{chunk_dir_name}_{i}.txt", "w", newline="", encoding="utf8") as file:
        file.write(data)

