import glob
import re
import os
from tqdm import tqdm
from collections import OrderedDict
import shutil
class Chunker:

    def __init__(self, directory, output_dir):
        self.directory = directory
        self.chunks = []
        self.output_dir = output_dir


    def re_match(self, text, pattern):
        pattern = r'(<\|det\|>(.*?)<\|/det\|>)'
        matches = re.findall(pattern, text, re.DOTALL)

        # pattern1 = r'<\|ref\|>.*?<\|/ref\|>\n'
        # new_text1 = re.sub(pattern1, '', text, flags=re.DOTALL)

        mathes_image = []
        mathes_other = []
        for a_match in matches:
            if '<|ref|>image<|/ref|>' in a_match[0]:
                mathes_image.append(a_match[0])
            else:
                mathes_other.append(a_match[0])
        return matches, mathes_image, mathes_other


    def extract_patches(self, directory='.'):
        """
        Extracts structured patches from all .mmd files in the specified directory.

        Returns:
            list of dict: Each dict represents a content patch with keys:
                - 'title': str (from filename)
                - 'subtitle': str or None
                - 'type': str ('text' or 'table')
                - 'content': str
        """
        patches = []
        # Pattern to match a tag followed by its content (until next tag or EOF)
        # pattern = re.compile(r'<\|ref\|>(?P<type>text|table|sub_title)<\|/ref\|>(?P<content>.*?)(?=<\|ref\|>|$)', re.DOTALL)
        pattern = re.compile(r'<\|ref\|>(?P<type>text|table|H1. sub_title|H2. sub_title|H3. sub_title|H4. sub_title|'
                             r'H5. sub_title|H6. sub_title|H7. sub_title)<\|/ref\|>(?P<content>.*?)(?=<\|ref\|>|$)', re.DOTALL)

        for filename in glob.glob(os.path.join(directory, "*.txt")):
            # Extract title from filename (remove extension)
            title = os.path.splitext(os.path.basename(filename))[0].replace('text', '')

            with open(filename, 'r', encoding='utf-8') as f:
                content = f.read()

            matches, mathes_image, mathes_other = self.re_match(content, pattern)
            for idx, a_match_other in enumerate(tqdm(mathes_other, desc="other")):
                content = content.replace(a_match_other, '').replace('\\coloneqq', ':=').replace('\\eqqcolon', '=:')


            chunk_template = {
                        'title': title,
                        'H1. sub_title': None,
                        'H2. sub_title': None,
                        'H3. sub_title': None,
                        'H4. sub_title': None,
                        'H5. sub_title': None,
                        'H6. sub_title': None,
                        'H7. sub_title': None,
                        'text': None,
                        'table': None,
                    }

            # Find all tagged sections
            chunk = chunk_template.copy()
            previous_heading_number = 1

            for match in pattern.finditer(content):
                section_type = match.group('type').replace("\u200c", " ")#.replace("\n", " ")
                section_content = match.group('content').strip().replace("\u200c", " ")#.replace("\n", " ")

                if "sub_title" in section_type:
                    heading_number = int(section_type[1])

                    for i in range(heading_number + 1, 8):
                        chunk[f"H{i}. sub_title"] = None

                chunk[section_type] = section_content

                if section_type == 'text' or section_type == 'table':
                    patches.append(chunk.copy())
                    chunk[section_type] = None

        nonnul_patches = []
        for patch in patches:
            nonnul_patches.append({k: v for k, v in patch.items() if v is not None})

        return nonnul_patches


    def file_and_h1_chunking(self, nonul_patches):
        files = [patch['title'] for patch in nonul_patches]
        files = list(OrderedDict.fromkeys(files))
        file_h1_patches = []
        for file in files:
            file_patches = [patch for patch in nonul_patches if patch['title'] == file]

            H1s = [patch['H1. sub_title'] for patch in file_patches ]
            H1s = list(OrderedDict.fromkeys(H1s))

            for h1 in H1s:
                h1_content = ""
                for patch in file_patches:
                    if patch['H1. sub_title'] == h1:

                        for key, value in patch.items():
                            if key not in ['H1. sub_title', 'title']:
                                h1_content += "\n" + value

                file_h1_patches.append(f'title: {file} \nH1. sub_title: {h1} \ncontent: {h1_content}')

        return file_h1_patches


    def ref_text_chunking(self, nonul_patches):

        ref_text_chunks = []
        for patch in nonul_patches:

          if "text" in patch.keys():
            ref_text_chunks.append(f'title: {patch["title"]} \nH1. sub_title: {patch["H1. sub_title"]} \ncontent: {patch["text"]}')

          if "table" in patch.keys():
              ref_text_chunks.append(f'title: {patch["title"]} \nH1. sub_title: {patch["H1. sub_title"]} \ncontent: {patch["table"]}')

        return ref_text_chunks


    def merge_and_write(self, text_chunks, h1_chunks):

        extracted_text_chunks_dir = os.path.join(self.output_dir, 'extracted_text_chunks')
        os.makedirs(extracted_text_chunks_dir, exist_ok=True)

        extracted_h1_chunks_dir = os.path.join(self.output_dir, 'extracted_h1_chunks')
        os.makedirs(extracted_h1_chunks_dir, exist_ok=True)

        for idx, text_chunk  in enumerate(text_chunks):

            pattern = r'title:\s*(.+)'
            match = re.search(pattern, text_chunk)

            if match:
                title = match.group(1).strip()
                print(f"Title (Method 2): {title}")

                if not os. path. isdir(os.path.join(extracted_text_chunks_dir, title)):
                    os.makedirs(os.path.join(extracted_text_chunks_dir, title), exist_ok=True)


            with open(os.path.join(os.path.join(extracted_text_chunks_dir, title), str(idx)), 'w', encoding='utf-8') as f:
                f.write(text_chunk)

        for idx, h1_chunk in enumerate(h1_chunks):

            match = re.search(pattern, h1_chunk)

            if match:
                title = match.group(1).strip()
                # print(f"Title (Method 2): {title}")

                if not os.path.isdir(os.path.join(extracted_h1_chunks_dir, title)):
                    os.makedirs(os.path.join(extracted_h1_chunks_dir, title), exist_ok=True)


                with open(os.path.join(os.path.join(extracted_h1_chunks_dir, title), str(idx)), 'w', encoding='utf-8') as f:
                    f.write(h1_chunk)

        return text_chunks, h1_chunks

    def extract_doc_specific_chunks(self):
        extracted_chunks_dir = os.path.join(self.output_dir)
        doc_specific_chunks_dir = os.path.join(self.output_dir, 'doc_specific_chunks')

        os.makedirs(doc_specific_chunks_dir, exist_ok=True)
        doc_names = os.listdir(os.path.join(extracted_chunks_dir, 'extracted_h1_chunks'))

        for doc_name in doc_names:
            os.makedirs(os.path.join(doc_specific_chunks_dir, doc_name), exist_ok=True)
            os.makedirs(os.path.join(doc_specific_chunks_dir, doc_name, 'extracted_h1_chunks'), exist_ok=True)
            os.makedirs(os.path.join(doc_specific_chunks_dir, doc_name, 'extracted_text_chunks'), exist_ok=True)

            chunk_levels = ['extracted_h1_chunks', 'extracted_text_chunks']
            for chunk_level in chunk_levels:
                chunks = os.listdir(os.path.join(extracted_chunks_dir, chunk_level, doc_name))


                for idx, chunk_file in enumerate(sorted(chunks)):
                    chunk_path = os.path.join(extracted_chunks_dir, chunk_level, doc_name, f"{chunk_file}")

                    chunk_new_path = os.path.join(doc_specific_chunks_dir, doc_name, chunk_level, chunk_file)

                    if chunk_level == 'extracted_h1_chunks':

                        chunk_new_path = chunk_new_path.replace(chunk_file, str(idx)) + f"_{doc_name}_H.txt"

                    else:
                        chunk_new_path = chunk_new_path.replace(chunk_file, str(idx))  + f"_{doc_name}_T.txt"

                    shutil.copyfile(chunk_path, chunk_new_path)


                        # file will be renamed
if __name__ == '__main__':

    # Example usage:
    directory_path = "/home/hooman/PycharmProjects/RegAssist/mahboubi_output_texts_checked"
    output_path = f"{directory_path}/extracted_chunks"
    chunker = Chunker(directory_path, output_path)
    nonul_patches = chunker.extract_patches(directory_path)
    h1_chunks = chunker.file_and_h1_chunking(nonul_patches)
    text_chunks = chunker.ref_text_chunking(nonul_patches)

    chunker.merge_and_write(text_chunks, h1_chunks)
    chunker.extract_doc_specific_chunks()
    print("chucks were merged and written")


