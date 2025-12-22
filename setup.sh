#!/bin/bash

echo "Setting up LLMs.txt Generator..."

# Backend setup
echo "Setting up backend..."
cd backend

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

echo "Activating virtual environment..."
source venv/bin/activate

echo "Installing Python dependencies..."
pip install -r requirements.txt

# Check for .env file
if [ ! -f ".env" ]; then
    echo "Creating .env file..."
    echo "# OpenAI API Key (optional - get from https://platform.openai.com/api-keys)" > .env
    echo "OPENAI_API_KEY=" >> .env
    echo "" >> .env
    echo "# Database path (optional, defaults to database.db)" >> .env
    echo "DB_PATH=database.db" >> .env
    echo "" >> .env
    echo "# Flask port (optional, defaults to 5001)" >> .env
    echo "FLASK_PORT=5001" >> .env
    echo "⚠️  Created .env file. Add your OPENAI_API_KEY if you want LLM features."
else
    echo "✓ .env file already exists"
fi

echo "Initializing database..."
python -c "from models import init_db; init_db()"

cd ..

# Frontend setup
echo "Setting up frontend..."
cd frontend

echo "Installing Node dependencies..."
npm install

cd ..

echo ""
echo "✅ Setup complete!"
echo ""
echo "📝 Next steps:"
echo "1. Make sure backend/.env has your OPENAI_API_KEY"
echo ""
echo "2. To start the backend (Terminal 1):"
echo "   cd backend"
echo "   source venv/bin/activate"
echo "   python app.py"
echo ""
echo "3. To start the frontend (Terminal 2):"
echo "   cd frontend"
echo "   npm start"
echo ""
echo "4. Open http://localhost:3000 in your browser"


