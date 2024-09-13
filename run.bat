@echo off
REM Python sanal ortamı oluşturma ve aktive etme
python -m venv venv
call venv\Scripts\activate

REM Gerekli kütüphaneleri yükleme
pip install --upgrade pip
pip install -r requirements.txt

REM Django migrasyonları yapma
python manage.py makemigrations
python manage.py migrate

REM Django sunucusunu başlatma
python manage.py runserver
