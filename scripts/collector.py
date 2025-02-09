from supabase import create_client
from mistralai.client import MistralClient
from mistralai.models.chat_completion import ChatMessage
import requests
from bs4 import BeautifulSoup
import os
import json
import logging
from datetime import datetime
import hashlib

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialisation des clients
supabase = create_client(
    os.environ.get("SUPABASE_URL"),
    os.environ.get("SUPABASE_KEY")
)

mistral = MistralClient(
    api_key=os.environ.get("MISTRAL_API_KEY")
)

def get_document_hash(content):
    """Génère un hash unique pour un document"""
    return hashlib.sha256(content.encode()).hexdigest()

def classify_document(title, content):
    """Classifie le document avec Mistral AI"""
    try:
        prompt = f"""
        Analysez ce document fiscal/juridique et classifiez-le.
        
        TITRE: {title}
        CONTENU: {content[:500]}...
        
        1. Identifiez le thème principal parmi:
        - Pacte Dutreil
        - DMTG
        - Location meublée
        - Revenus fonciers
        - Plus-values particuliers
        - Plus-values immobilières
        - Plus-values professionnelles
        - BA
        
        2. Identifiez le type de document parmi:
        - Loi
        - Décret
        - Arrêté
        - Instruction fiscale
        - Réponse ministérielle
        - Jurisprudence
        
        Répondez uniquement au format JSON:
        {{"theme": "nom_du_theme", "category": "type_de_document"}}
        """
        
        messages = [
            ChatMessage(role="system", content="Vous êtes un expert en classification de documents juridiques et fiscaux."),
            ChatMessage(role="user", content=prompt)
        ]
        
        response = mistral.chat(
            model="mistral-medium",
            messages=messages
        )
        
        result = json.loads(response.choices[0].message.content)
        return result
        
    except Exception as e:
        logger.error(f"Erreur de classification: {str(e)}")
        return None

def collect_bofip():
    """Collecte les documents du BOFIP"""
    try:
        url = "https://bofip.impots.gouv.fr/bofip/flux-rss/"
        response = requests.get(url)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'xml')
            items = soup.find_all('item')
            
            for item in items:
                title = item.title.text if item.title else ''
                content = item.description.text if item.description else ''
                doc_hash = get_document_hash(content)
                
                # Vérification des doublons
                existing = supabase.table('documents').select('id').eq('document_hash', doc_hash).execute()
                
                if not existing.data:
                    classification = classify_document(title, content)
                    if classification:
                        # Récupération des IDs
                        theme = supabase.table('fiscal_themes').select('id').eq('name', classification['theme']).execute()
                        category = supabase.table('document_categories').select('id').eq('name', classification['category']).execute()
                        
                        document = {
                            'title': title,
                            'content': content,
                            'theme_id': theme.data[0]['id'] if theme.data else None,
                            'category_id': category.data[0]['id'] if category.data else None,
                            'publication_date': datetime.now().date().isoformat(),
                            'source_url': item.link.text if item.link else '',
                            'document_hash': doc_hash
                        }
                        
                        supabase.table('documents').insert(document).execute()
                        logger.info(f"Document ajouté: {title}")
    
    except Exception as e:
        logger.error(f"Erreur lors de la collecte BOFIP: {str(e)}")

def main():
    """Fonction principale"""
    logger.info("Début de la collecte")
    collect_bofip()
    logger.info("Fin de la collecte")

if __name__ == "__main__":
    main()
