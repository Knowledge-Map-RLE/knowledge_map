"""
UDPipe Adapter for Universal Dependencies parsing.

Provides tokenization, POS tagging, lemmatization and dependency parsing.
"""

from typing import List, Dict, Any, Optional
import os
import subprocess
import sys

from ..unified_types import (
    UnifiedToken,
    UnifiedDependency,
    UnifiedEntity,
    UnifiedSentence,
    UnifiedDocument,
    ProcessorOutput,
)


class UDPipeAdapter:
    """Adapter for UDPipe (Universal Dependencies pipeline)."""

    def __init__(self, model_path: Optional[str] = None, lang: str = "en"):
        """
        Initialize UDPipe adapter.

        Args:
            model_path: Path to UDPipe model file (.udpipe)
            lang: Language code (default: 'en' for English)
        """
        self.lang = lang
        self.model_path = model_path
        self.model = None
        self.processor_name = "udpipe"

        # Try to import ufal.udpipe
        try:
            import ufal.udpipe as udpipe
            self.udpipe = udpipe
            # Get version - ufal.udpipe doesn't have Model.version(), use package version
            try:
                import importlib.metadata
                self.version = importlib.metadata.version('ufal.udpipe')
            except:
                self.version = "1.3"  # Default version
        except ImportError:
            print("ufal.udpipe not installed, attempting to install...")
            try:
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install", "ufal.udpipe"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                import ufal.udpipe as udpipe
                self.udpipe = udpipe
                try:
                    import importlib.metadata
                    self.version = importlib.metadata.version('ufal.udpipe')
                except:
                    self.version = "1.3"
                print("Successfully installed and loaded ufal.udpipe")
            except Exception as e:
                print(f"Failed to install ufal.udpipe: {e}")
                self.udpipe = None
                self.version = "unavailable"
                return

        # Load or download model
        if model_path and os.path.exists(model_path):
            self._load_model(model_path)
        else:
            self._download_and_load_model()

    def _load_model(self, model_path: str):
        """Load UDPipe model from file."""
        if not self.udpipe:
            return

        self.model = self.udpipe.Model.load(model_path)
        if not self.model:
            print(f"Failed to load UDPipe model from {model_path}")
        else:
            print(f"Loaded UDPipe model from {model_path}")

    def _download_and_load_model(self):
        """Download and load English UDPipe model."""
        if not self.udpipe:
            return

        # Try to download english-ewt model (English Web Treebank) from UD 2.5
        # Direct download link from GitHub mirror
        model_url = "https://raw.githubusercontent.com/jwijffels/udpipe.models.ud.2.5/master/inst/udpipe-ud-2.5-191206/english-ewt-ud-2.5-191206.udpipe"
        model_filename = "english-ewt-ud-2.5-191206.udpipe"

        # Create models directory
        models_dir = os.path.join(os.path.dirname(__file__), "..", "..", "models")
        os.makedirs(models_dir, exist_ok=True)
        model_path = os.path.join(models_dir, model_filename)

        if os.path.exists(model_path):
            print(f"Found existing UDPipe model at {model_path}")
            self._load_model(model_path)
            return

        # Download model
        print(f"Downloading UDPipe model from {model_url}...")
        try:
            import urllib.request
            urllib.request.urlretrieve(model_url, model_path)
            print(f"Downloaded UDPipe model to {model_path}")
            self._load_model(model_path)
        except Exception as e:
            print(f"Failed to download UDPipe model: {e}")
            print("UDPipe will not be available for this session")

    def process_text(self, text: str) -> ProcessorOutput:
        """
        Process text with UDPipe and return ProcessorOutput.

        Args:
            text: Input text

        Returns:
            ProcessorOutput with tokens, dependencies, and entities
        """
        if not self.model or not self.udpipe:
            return ProcessorOutput(
                processor_name=self.processor_name,
                processor_version=self.version,
                tokens=[],
                dependencies=[],
                entities=[]
            )

        # Process text
        tokenizer = self.model.newTokenizer(self.udpipe.Model.DEFAULT)
        if not tokenizer:
            return ProcessorOutput(
                processor_name=self.processor_name,
                processor_version=self.version,
                tokens=[],
                dependencies=[],
                entities=[]
            )

        # Tokenize
        sentence = self.udpipe.Sentence()
        tokenizer.setText(text)

        output = ProcessorOutput(
            processor_name=self.processor_name,
            processor_version=self.version,
            tokens=[],
            dependencies=[],
            entities=[]
        )

        token_offset = 0  # Global token index

        # Process all sentences
        while tokenizer.nextSentence(sentence):
            # Perform tagging and parsing
            self.model.tag(sentence, self.udpipe.Model.DEFAULT)
            self.model.parse(sentence, self.udpipe.Model.DEFAULT)

            # Extract tokens
            for i in range(1, sentence.words.size()):  # Skip index 0 (root)
                word = sentence.words[i]

                # Create UnifiedToken
                token = UnifiedToken(
                    idx=token_offset,
                    text=word.form,
                    start_char=0,  # UDPipe doesn't provide character offsets
                    end_char=0,
                    lemma=word.lemma or word.form.lower(),
                    pos=word.upostag or 'X',  # Universal POS tag
                    pos_fine=word.xpostag or '',  # Language-specific POS tag
                    morph=self._parse_feats(word.feats),
                    is_stop=word.form.lower() in {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for'},
                    is_punct=word.upostag == 'PUNCT',
                    is_space=word.form.isspace(),
                    confidence=0.85,
                    sources=[f'{self.processor_name}-{self.version}']
                )
                output.tokens.append(token)

                # Extract dependencies (head is 1-indexed in UDPipe)
                if word.head > 0:  # Not root
                    dep = UnifiedDependency(
                        head_idx=(word.head - 1) + token_offset,  # Convert to 0-indexed and add offset
                        dependent_idx=(i - 1) + token_offset,  # Convert to 0-indexed and add offset
                        relation=word.deprel or 'dep',
                        confidence=0.85,
                        sources=[f'{self.processor_name}-{self.version}']
                    )
                    output.dependencies.append(dep)

            token_offset += sentence.words.size() - 1  # Update offset (exclude root)
            sentence = self.udpipe.Sentence()  # Create new sentence for next iteration

        return output

    def _parse_feats(self, feats: str) -> Dict[str, str]:
        """Parse morphological features from UDPipe format."""
        if not feats or feats == '_':
            return {}

        feats_dict = {}
        for feat in feats.split('|'):
            if '=' in feat:
                key, value = feat.split('=', 1)
                feats_dict[key] = value
        return feats_dict

    def get_processor_name(self) -> str:
        """Get processor name."""
        return self.processor_name

    def get_processor_version(self) -> str:
        """Get processor version."""
        return self.version
