# PDF в изображения AWS Lambda

Бессерверная функция AWS Lambda, которая конвертирует PDF-файлы в изображения PNG. Функция принимает загрузки PDF, конвертирует каждую страницу в изображение PNG и сохраняет их в S3. Она включает веб-интерфейс для удобного тестирования и функцию автоматического дедупликации изображений с использованием контрольных сумм SHA256.

## Возможности

- Конвертация PDF-файлов в отдельные изображения PNG
- Автоматическая дедупликация изображений с использованием контрольных сумм SHA256
- Хранение изображений в S3 с путями на основе содержимого (`s3://<bucket-name>/pages/<sha256>.png`)
- Веб-интерфейс для тестирования
- Поддержка CORS для доступа из браузера
- Безопасные предварительно подписанные URL для прямых загрузок в S3

## Архитектура

### Компоненты AWS
- **AWS Lambda**: Обрабатывает PDF и конвертирует изображения
- **Amazon S3**: Хранит загруженные PDF и конвертированные изображения
- **Lambda Function URL**: Предоставляет HTTP-конечную точку для функции

### Структура файлов
```
.
├── README.md
├── template.yaml             # SAM шаблон для ресурсов AWS
├── deps
│   ├── build_layer.sh       # Скрипт для создания Lambda слоя с Poppler
│   └── requirements.txt      # Зависимости Python
├── src
│   └── app.py               # Код функции Lambda
└── test_lambda.html         # Веб-интерфейс для тестирования
```

## API Endpoints

Функция Lambda предоставляет следующие конечные точки через свой Function URL:

1. **Получить URL для загрузки** (`GET /?type=get_upload_url`)
   - Возвращает предварительно подписанный URL для загрузки PDF в S3
   - Ответ: `{ "uploadUrl": "...", "fileId": "..." }`

2. **Обработать PDF** (`GET /?type=process&fileId=<file-id>`)
   - Конвертирует загруженный PDF в изображения
   - Ответ: `{ "imageUrls": ["...", "..."] }`

## Дедупликация изображений

Функция использует контрольные суммы SHA256 для дедупликации изображений:
1. Каждая страница PDF конвертируется в изображение PNG
2. Для каждого изображения вычисляется контрольная сумма SHA256
3. Изображения сохраняются по пути `pages/<sha256>.png`
4. Если изображение с такой же контрольной суммой уже существует, оно повторно используется вместо повторной загрузки

Это обеспечивает:
- Идентичные изображения хранятся только один раз
- Изображения могут быть общими для разных PDF
- Оптимизация использования хранилища
- URL изображений детерминированы и основаны на содержимом

## Пример использования в React

Вот как использовать API в приложении React:

```jsx
import { useState } from 'react';

const PdfConverter = () => {
  const [images, setImages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Замените на ваш Lambda Function URL
  const LAMBDA_URL = 'your-lambda-url-here';

  const handleFileChange = async (event) => {
    const file = event.target.files[0];
    if (!file || file.type !== 'application/pdf') {
      setError('Пожалуйста, выберите PDF-файл');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      // Шаг 1: Получить URL для загрузки
      const urlResponse = await fetch(`${LAMBDA_URL}?type=get_upload_url`);
      if (!urlResponse.ok) throw new Error('Не удалось получить URL для загрузки');
      const { uploadUrl, fileId } = await urlResponse.json();

      // Шаг 2: Загрузить PDF
      const uploadResponse = await fetch(uploadUrl, {
        method: 'PUT',
        body: file,
        headers: {
          'Content-Type': 'application/pdf'
        }
      });
      if (!uploadResponse.ok) throw new Error('Не удалось загрузить PDF');

      // Шаг 3: Обработать PDF и получить изображения
      await new Promise(resolve => setTimeout(resolve, 2000)); // Подождать для согласованности S3
      const processResponse = await fetch(`${LAMBDA_URL}?type=process&fileId=${fileId}`);
      if (!processResponse.ok) throw new Error('Не удалось обработать PDF');
      const { imageUrls } = await processResponse.json();

      setImages(imageUrls);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <input
        type="file"
        accept=".pdf"
        onChange={handleFileChange}
        disabled={loading}
      />
      
      {loading && <div>Конвертация PDF...</div>}
      {error && <div style={{ color: 'red' }}>{error}</div>}
      
      <div style={{ 
        display: 'grid', 
        gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
        gap: '1rem',
        padding: '1rem'
      }}>
        {images.map((url, index) => (
          <img
            key={url}
            src={url}
            alt={`Страница ${index + 1}`}
            style={{
              width: '100%',
              height: 'auto',
              boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
            }}
          />
        ))}
      </div>
    </div>
  );
};

export default PdfConverter;
```

## Настройка и развертывание

1. Установите необходимые компоненты:
   - AWS SAM CLI
   - Docker (для создания Lambda слоя)
   - Git (для клонирования репозитория)

2. Клонируйте этот репозиторий:
   ```bash
   git clone https://github.com/ai-1st/pdf-to-image-aws-lambda.git
   cd pdf-to-image-aws-lambda
   ```

3. Создайте Lambda слой (см. раздел [Создание Lambda слоя](#создание-lambda-слоя) для подробностей):
   ```bash
   cd deps
   chmod +x build_layer.sh
   ./build_layer.sh
   cd ..
   ```

4. Разверните с помощью SAM:
   ```bash
   sam build
   sam deploy --guided
   ```

## Создание Lambda слоя

Перед развертыванием необходимо создать Lambda слой, содержащий Poppler и другие зависимости. Слой создается с использованием Docker для обеспечения совместимости со средой Lambda.

### Предварительные требования
- Установлен и запущен Docker
- AWS SAM CLI
- Оболочка Bash

### Шаги сборки

1. Перейдите в директорию `deps`:
   ```bash
   cd deps
   ```

2. Сделайте скрипт сборки исполняемым:
   ```bash
   chmod +x build_layer.sh
   ```

3. Запустите скрипт сборки:
   ```bash
   ./build_layer.sh
   ```

Скрипт выполнит:
- Создание Docker-контейнера на основе образа AWS Lambda Python 3.13 ARM64
- Установку системных пакетов, включая Poppler и его зависимости
- Установку пакетов Python из requirements.txt
- Копирование необходимых бинарных файлов и общих библиотек
- Создание директории слоя с правильной структурой
- Очистку временных файлов

Результирующий слой будет создан в директории `deps/layer` со следующей структурой:
```
layer/
├── bin/          # Бинарные файлы Poppler (pdfinfo, pdftoppm, pdftocairo)
├── lib/          # Общие библиотеки
└── python/       # Пакеты Python
```

## Тестирование

1. Откройте `test_lambda.html` в веб-браузере
2. Введите ваш Lambda Function URL
3. Загрузите PDF-файл
4. Просмотрите конвертированные изображения в сетке

## Зависимости

- Python 3.8+
- pdf2image
- boto3
- Poppler (установлен в Lambda слое)

## Переменные окружения

- `BUCKET_NAME`: Имя S3-бакета для хранения файлов

## Безопасность

- CORS включен для доступа из браузера
- Предварительно подписанные URL для безопасных загрузок в S3
- Публичный Lambda Function URL с контролем CORS

## Обработка ошибок

Функция включает комплексную обработку ошибок для:
- Недопустимых типов файлов
- Неудачных конвертаций
- Проблем с загрузкой/скачиванием S3
- Проблем с CORS и предварительно подписанными URL

## Вклад в проект

Не стесняйтесь открывать issues или отправлять pull requests для улучшений.

## Лицензия

MIT License
