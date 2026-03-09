FROM python:3.13-bookworm

# Install wkhtmltoimage
RUN wget https://github.com/wkhtmltopdf/packaging/releases/download/0.12.6.1-3/wkhtmltox_0.12.6.1-3.bookworm_amd64.deb
RUN apt update && apt install ./wkhtmltox*bookworm_amd64.deb

WORKDIR /code
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY ./ .

ENTRYPOINT [ "python", "/code/bot.py" ]