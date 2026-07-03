"""
Setup and validate NLP models.

This module ensures all required NLP models are downloaded and cached
before the gRPC server starts. Models are cached in MODEL_CACHE_DIR
to avoid re-downloading on each restart.
"""

import logging
import os
import sys
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from config import get_config


def setup_nltk_models():
    """Download and cache NLTK data."""
    try:
        import nltk
        
        config = get_config()
        cache_dir = config.model_cache_dir / "nltk_data"
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Add to NLTK path so it uses our cache
        nltk.data.path.insert(0, str(cache_dir))
        
        # List of required NLTK data packages
        required_packages = [
            'punkt',
            'averaged_perceptron_tagger',
            'wordnet',
            'omw-1.4',
            'stopwords'
        ]
        
        logger.info(f"Setting up NLTK models in {cache_dir}")
        
        for package in required_packages:
            try:
                # Check if package exists
                nltk.data.find(f'tokenizers/{package}')
                logger.info(f"  ✓ NLTK {package} already cached")
            except LookupError:
                # Package not found, download it
                logger.info(f"  → Downloading NLTK {package}...")
                try:
                    nltk.download(package, download_dir=str(cache_dir), quiet=True)
                    logger.info(f"  ✓ NLTK {package} downloaded")
                except Exception as e:
                    logger.warning(f"  ✗ Failed to download NLTK {package}: {e}")
        
        logger.info("NLTK setup complete")
        return True
        
    except ImportError:
        logger.warning("NLTK not installed, skipping NLTK setup")
        return False
    except Exception as e:
        logger.error(f"Error setting up NLTK: {e}")
        return False


def setup_spacy_models():
    """Download and cache spaCy models."""
    try:
        import spacy
        import importlib
        
        config = get_config()
        
        if not config.enable_spacy:
            logger.info("spaCy disabled in config, skipping spaCy setup")
            return True
        
        model = config.spacy_model
        logger.info(f"Loading spaCy model: {model}")

        # Activate GPU if available (requires cupy, now installed)
        try:
            spacy.require_gpu()
            logger.info("  GPU activated (cupy backend)")
        except Exception:
            logger.info("  GPU not available, using CPU")

        try:
            nlp = spacy.load(model)
            logger.info(f"  ✓ spaCy model '{model}' loaded")
            return True
        except Exception as e:
            logger.error(f"  ✗ Failed to load spaCy model '{model}': {e}")
            return False
                
    except ImportError:
        logger.warning("spaCy not installed, skipping spaCy setup")
        return False
    except Exception as e:
        logger.error(f"Error setting up spaCy: {e}")
        return False


def setup_stanza_models():
    """Download and cache Stanza models."""
    try:
        import stanza
        
        config = get_config()
        
        if not config.enable_stanza:
            logger.info("Stanza disabled in config, skipping Stanza setup")
            return True
        
        lang = config.stanza_lang
        cache_dir = config.model_cache_dir / "stanza_models"
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Try biomedical/clinical packages first (Stanza provides named biomed packages)
        bio_packages = ["genia", "craft", "mimic"]
        logger.info(f"Setting up Stanza models for language: {lang}; trying bio packages: {bio_packages}")
        
        # Set Stanza home to use our cache directory
        os.environ['STANZA_HOME'] = str(cache_dir)
        
        # First try biomedical/clinical packages
        for pkg in bio_packages:
            try:
                logger.info(f"  → Checking Stanza biomedical package '{pkg}'...")
                # Attempt to construct pipeline using the package name
                nlp = stanza.Pipeline(lang=lang, processors='tokenize,pos,lemma,depparse', package=pkg)
                logger.info(f"  ✓ Stanza biomed package '{pkg}' available and loaded")
                return True
            except Exception:
                logger.info(f"  - Stanza package '{pkg}' not available locally")
                try:
                    logger.info(f"  → Downloading Stanza package '{pkg}' for lang '{lang}'")
                    stanza.download(lang, package=pkg, processors='tokenize,pos,lemma,depparse')
                    nlp = stanza.Pipeline(lang=lang, processors='tokenize,pos,lemma,depparse', package=pkg)
                    logger.info(f"  ✓ Stanza biomed package '{pkg}' downloaded and loaded")
                    return True
                except Exception as e:
                    logger.info(f"  - Failed to download/load package '{pkg}': {e}")

        # Fallback: try default English pipeline
        try:
            logger.info(f"  → Trying default Stanza pipeline for '{lang}'")
            nlp = stanza.Pipeline(lang=lang, processors='tokenize,pos,lemma,depparse')
            logger.info(f"  ✓ Stanza default models for '{lang}' available")
            return True
        except Exception:
            logger.info(f"  → Downloading default Stanza pipeline for '{lang}'")
            try:
                stanza.download(lang, processors='tokenize,pos,lemma,depparse')
                nlp = stanza.Pipeline(lang=lang, processors='tokenize,pos,lemma,depparse')
                logger.info(f"  ✓ Stanza models for '{lang}' downloaded and verified")
                return True
            except Exception as download_error:
                logger.error(f"  ✗ Failed to download Stanza models: {download_error}")
                return False
        
    except ImportError:
        logger.warning("Stanza not installed, skipping Stanza setup")
        return False
    except Exception as e:
        logger.error(f"Error setting up Stanza: {e}")
        return False


def setup_hf_transformers_cache():
    """Setup Hugging Face transformers cache directory."""
    try:
        config = get_config()
        cache_dir = config.model_cache_dir / "huggingface"
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Set HF cache environment variables
        os.environ['HF_HOME'] = str(cache_dir)
        os.environ['TRANSFORMERS_CACHE'] = str(cache_dir / "hub")
        os.environ['HF_HUB_CACHE'] = str(cache_dir / "hub")
        
        logger.info(f"Hugging Face cache directory: {cache_dir}")
        
        # If token is set, it's already in environment from grpc_server
        hf_token = os.environ.get('HUGGING_FACE_TOKEN')
        if hf_token:
            logger.info("Hugging Face token configured for authenticated access")

        # Try to proactively download preferred HF models (bio -> sci -> general)
        try:
            from transformers import AutoTokenizer, AutoModel
            hub_cache = cache_dir / "hub"
            hub_cache.mkdir(parents=True, exist_ok=True)

            candidates = []
            if hasattr(config, 'hf_preferred_bio_models') and config.hf_preferred_bio_models:
                candidates.extend(config.hf_preferred_bio_models)
            if hasattr(config, 'hf_preferred_sci_models') and config.hf_preferred_sci_models:
                candidates.extend(config.hf_preferred_sci_models)

            # Deduplicate while preserving order
            seen = set()
            candidates = [x for x in candidates if not (x in seen or seen.add(x))]

            logger.info(f"Hugging Face model candidates (priority): {candidates}")

            # Limit HF pre-caching attempts to top-3 preferred models
            for model_id in candidates[:3]:
                try:
                    logger.info(f"  → Trying to cache HF model/tokenizer: {model_id}")
                    AutoTokenizer.from_pretrained(model_id, cache_dir=str(hub_cache), use_auth_token=hf_token)
                    # load model weights (small risk: large download) — attempt AutoModel first
                    try:
                        AutoModel.from_pretrained(model_id, cache_dir=str(hub_cache), use_auth_token=hf_token)
                        logger.info(f"    ✓ Cached model {model_id}")
                        # stop after first successful model (we only need 1 preferred)
                        break
                    except Exception as m_err:
                        logger.info(f"    - Tokenizer cached but model weights failed for {model_id}: {m_err}")
                except Exception as e:
                    logger.info(f"    - Failed to cache HF model/tokenizer {model_id}: {e}")
        except Exception as e:
            logger.info(f"  - transformers not available or caching failed: {e}")

        return True
        
    except Exception as e:
        logger.error(f"Error setting up HF transformers cache: {e}")
        return False


def setup_all_models():
    """
    Setup and validate all NLP models.
    
    This function ensures all required models are available before
    the gRPC server starts processing requests.
    
    Returns:
        bool: True if all critical setups succeeded, False otherwise
    """
    config = get_config()
    
    logger.info("=" * 60)
    logger.info("Starting NLP Model Setup")
    logger.info("=" * 60)
    
    # Create cache directory
    config.model_cache_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Model cache directory: {config.model_cache_dir}")
    
    # Setup each component
    results = {
        'nltk': setup_nltk_models() if config.enable_nltk else None,
        'spacy': setup_spacy_models() if config.enable_spacy else None,
        'stanza': setup_stanza_models() if config.enable_stanza else None,
        'hf_transformers': None,  # HF transformers кэширование отключено
    }
    
    logger.info("=" * 60)
    logger.info("Model Setup Summary:")
    logger.info("=" * 60)
    
    for component, success in results.items():
        if success is None:
            status = "SKIPPED"
        elif success:
            status = "✓ OK"
        else:
            status = "✗ FAILED"
        logger.info(f"  {component:20} {status}")
    
    logger.info("=" * 60)
    
    # Check if any critical setup failed
    critical = ['spacy', 'nltk']  # These are most commonly used
    failures = [k for k, v in results.items() if k in critical and v is False]
    
    if failures:
        logger.warning(f"Some critical models failed to setup: {failures}")
        logger.warning("Service may have limited functionality")
        return False
    
    logger.info("NLP models ready for use")
    return True


if __name__ == "__main__":
    # Allow running setup directly
    success = setup_all_models()
    sys.exit(0 if success else 1)
