import logging
import docopt
import pathlib
import html2text
import ebooklib
import ebooklib.epub
import shutil
import subprocess
import time
import os
import concurrent.futures
import platform


debug = False


data_path = pathlib.Path(__file__).resolve().parent / 'data'
if platform.system() == 'Darwin':
    tts_engine_path = data_path / 'bin' / 'mac' / 'tts_engine'
    ffmpeg_path = 'ffmpeg'
elif platform.system() == 'Windows':
    tts_engine_path = data_path / 'bin' / 'win32' / 'tts_engine' / 'tts_engine.exe'
    ffmpeg_path = data_path / 'bin' / 'win32' / 'ffmpeg' / 'bin' / 'ffmpeg.exe'


def run_tts_engine(text, output_wav_file):
    """Converts text to PCM audio data via calling tts_engine"""
    # todo: lang

    input_bytes = text.encode(encoding='utf-8', errors='strict')
    original_cwd = os.getcwd()

    try:
        os.chdir(tts_engine_path.parent)
        completed_process = subprocess.run(
            [str(tts_engine_path), '--lang', 'be', '--wav', str(output_wav_file)],
            input=input_bytes,
            check=True,
            text=False)
    finally:
        os.chdir(original_cwd)


def convert_pcm_to_mp3(wav_file, mp3_file):
    """Convert PCM data into MP3 data format by passing it through ffmpeg"""

    command = [
        str(ffmpeg_path),
        '-hide_banner',
        '-loglevel', 'warning',
        '-f', 's16le',
        '-ar', '48000',
        '-ac', '1',
        '-i', str(wav_file),
        str(mp3_file)
    ]

    subprocess.run(command, check=True)


def process_book_item(output_dir, id, idx, item):
    formatted_idx = '{:03d}'.format(idx)

    logging.info("Processing book item: %s %s", formatted_idx, item.get_name())

    h2t = html2text.HTML2Text()
    h2t.ignore_links = True
    h2t.ignore_images = True
    h2t.ignore_tables = True
    h2t.ignore_images = True
    h2t.images_to_alt = True
    #h2t.body_width = 0  # don't wrap

    body = item.get_body_content().decode("utf-8")
    clean_body = h2t.handle(body)

    chapter_path = output_dir / f'{formatted_idx}_{pathlib.Path(id).stem}'
    chapter_path_txt = chapter_path.with_suffix('.txt')
    chapter_path_wav = chapter_path.with_suffix('.wav')
    chapter_path_mp3 = chapter_path.with_suffix('.mp3')

    # only for debugging epub parsing
    with chapter_path_txt.open('w', encoding='utf-8') as f:
        f.write(clean_body)

    text = clean_body[0:1024] if debug else clean_body

    logging.info('%s: TTS start', formatted_idx)
    tts_start_time = time.time()
    run_tts_engine(text, chapter_path_wav)
    logging.info('%s: TTS complete (%s)', formatted_idx, time.time() - tts_start_time)

    # logging.info('%s: MP3 conversion start', formatted_idx)
    # mp3_start_time = time.time()
    # convert_pcm_to_mp3(chapter_path_wav, chapter_path_mp3)
    # logging.info('%s: MP3 conversion complete (%s)', formatted_idx, time.time() - mp3_start_time)

    # chapter_path_txt.unlink()
    # chapter_path_wav.unlink()


def process_book(input_epub_file):
    input_epub_file = pathlib.Path(input_epub_file).resolve()
    output_dir = input_epub_file.parent / input_epub_file.stem

    logging.info('Program started')
    logging.info('Input epub file: %s', input_epub_file)
    logging.info('Output directory: %s', output_dir)

    if not input_epub_file.exists():
        logging.error("Can't find input EPUB file: %s", input_epub_file)
        raise Exception()

    if output_dir.exists():
        logging.warning('Output directory exists. Removing it.')
        shutil.rmtree(output_dir, ignore_errors=True)

    output_dir.mkdir()

    book = ebooklib.epub.read_epub(input_epub_file)

    logging.info("Metadata id: %s", book.get_metadata('DC', 'identifier'))
    logging.info("Metadata title: %s", book.get_metadata('DC', 'title'))
    logging.info("Metadata language: %s", book.get_metadata('DC', 'language'))

    with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
        for idx, spine in enumerate(book.spine):
            id = spine[0]

            item = book.get_item_with_id(id)
            if item.get_type() != ebooklib.ITEM_DOCUMENT:
                continue

            executor.submit(process_book_item, output_dir, id, idx, item)

    logging.info('OK')


help = \
    """
    Sakrament EPUB reader
    
    Usage:
        sakrament-epub-reader <input_epub_file>
        sakrament-epub-reader (-h | --help) 
    """

def main():
    logging.basicConfig(
        level=logging.INFO,
        format='[%(thread)s]%(asctime)s ' + logging.BASIC_FORMAT,
        datefmt='[%H:%M:%S]')

    args = docopt.docopt(help)
    input_epub_file  = args['<input_epub_file>']

    process_book(input_epub_file)
