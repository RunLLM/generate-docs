## generate-docs
Update and maintain the documentation for your project with ease. 

Given an API file written in a supported language (eg. Python), this action will generate and maintain an OpenAPI spec file (in YAML format)
for that file, then open a pull request with the changes and an explanation.

## Requirements
The following Github Secrets must be accessible to the action:
** RUNLLM_API_KEY: The API key for your Runllm account.
** GITHUB_TOKEN: The Github token for the repository.

## Usage
This action is expected to be used only with push-based workflows. It is recommended to use this action by copy-pasting the following github workflow:

```yaml
name: Maintain OpenAPI Spec

on:
  push:
    branches: main
    path: 
      - '<path-to-your-api-file>'

permissions:
  contents: write
  pull-requests: write

jobs:
  update-docs:
    runs-on: ubuntu-latest
    steps:
      - name: Generate OpenAPI Documentation
        uses: runllm/generate-docs@v1
        with:
          runllm_api_key: ${{ secrets.RUNLLM_API_KEY }}
          github_token: ${{ secrets.GITHUB_TOKEN }}
          input_api_file: "<path-to-your-api-file>"
          output_spec_file: "<path-to-your-output-spec-file>"
          base_branch: "main" # Optional
```

## Example

Imagine we have added the following Github Action workflow:

```yaml
name: Maintain OpenAPI Spec

on:
  push:
    branches: main
    path: 
      - 'src/books_server.py'

permissions:
  contents: write
  pull-requests: write

jobs:
  update-docs:
    runs-on: ubuntu-latest
    steps:
      - name: Generate OpenAPI Documentation
        uses: runllm/generate-docs@v1
        with:
          runllm_api_key: ${{ secrets.RUNLLM_API_KEY }}
          github_token: ${{ secrets.GITHUB_TOKEN }}
          input_api_file: "src/books_server.py"
          output_spec_file: "docs/openapi.yml"
```

Now, let's say we create the following file at `src/books_server.py` and merge to main:


```python
from flask import Flask, jsonify, request, abort

app = Flask(__name__)

# In-memory database simulation
books = []

@app.route('/books', methods=['GET'])
def get_books():
    return jsonify(books)

@app.route('/books', methods=['POST'])
def add_book():
    if not request.json or 'title' not in request.json or 'author' not in request.json:
        abort(400)
    book = {
        'id': len(books) + 1,
        'title': request.json['title'],
        'author': request.json['author'],
        'isbn': request.json.get('isbn', ""),
        'publishedYear': request.json.get('publishedYear', None)
    }
    books.append(book)
    return jsonify(book), 201

@app.route('/books/<int:book_id>', methods=['GET'])
def get_book(book_id):
    book = next((book for book in books if book['id'] == book_id), None)
    if book is None:
        abort(404)
    return jsonify(book)

@app.route('/books/<int:book_id>', methods=['PUT'])
def update_book(book_id):
    book = next((book for book in books if book['id'] == book_id), None)
    if book is None:
        abort(404)
    if not request.json:
        abort(400)

    book['title'] = request.json.get('title', book['title'])
    book['author'] = request.json.get('author', book['author'])
    book['isbn'] = request.json.get('isbn', book['isbn'])
    book['publishedYear'] = request.json.get('publishedYear', book['publishedYear'])
    return jsonify(book)

@app.route('/books/<int:book_id>', methods=['DELETE'])
def delete_book(book_id):
    global books
    books = [book for book in books if book['id'] != book_id]
    return jsonify({'result': True})

if __name__ == '__main__':
    app.run(debug=True)
```

The action will automatically generate a pull request adding the following OpenAPI spec file at `docs/openapi.yml`:

```yaml
openapi: 3.0.0
info:
  title: Book Management API
  version: 1.0.0
  description: This API allows you to manage a collection of books. You can add, retrieve, update, and delete books.

paths:
  /books:
    get:
      summary: Retrieve a list of all books
      description: This endpoint returns a list of all books in the collection. Each book is represented with its unique ID, title, author, ISBN, and the year it was published.
      responses:
        '200':
          description: A list of books
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/Book'
    post:
      summary: Add a new book
      description: This endpoint allows you to add a new book to the collection. The title and author are required, while the ISBN and published year are optional.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/Book'
      responses:
        '201':
          description: The book was successfully created
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Book'
        '400':
          description: The request was invalid. Either the title or author was not provided.
  ...
```

Future edits to `src/book_server.py` will continously update the OpenAPI spec file and open corresponding pull requests with any updates. 
Never let your documentation get out of date again!