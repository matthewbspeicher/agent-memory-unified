<!DOCTYPE html>
<html>
<head>
    <title>Remembr API Docs</title>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <style>
        body { margin: 0; padding: 0; }
    </style>
</head>
<body>
    <script id="api-reference" data-url="/openapi.json"></script>
    <script>
      var configuration = {
        theme: 'purple',
        layout: 'modern',
        metaData: {
          title: 'Remembr API Reference',
        }
      }
      document.getElementById('api-reference').dataset.configuration = JSON.stringify(configuration)
    </script>
    <script src="https://cdn.jsdelivr.net/npm/@scalar/api-reference"></script>
</body>
</html>
