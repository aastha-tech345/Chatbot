"""
Test product image extraction from various API response formats.

Fixes issue: "Product images not showing in chatbot"

Tests that images are properly extracted from multiple field formats:
- image (simple field)
- image_url (snake_case)
- imageUrl (camelCase)
- thumbnail / thumbnail_url
- product_image / product_image_url
- media array (with url, image_url, or src fields)
"""

import pytest
from app.workflow import _trim_product


class TestProductImageExtraction:
    """Test image extraction from various product API response formats."""
    
    def test_extract_image_from_simple_image_field(self):
        """Test extraction from 'image' field."""
        product = {
            'id': 'p1',
            'name': 'Test Product',
            'image': 'https://api.example.com/images/product1.jpg',
            'price': 99.99,
        }
        result = _trim_product(product)
        
        assert 'image_url' in result, "image_url not extracted"
        assert result['image_url'] == 'https://api.example.com/images/product1.jpg'
    
    def test_extract_image_from_image_url_field(self):
        """Test extraction from 'image_url' field (snake_case)."""
        product = {
            'id': 'p1',
            'name': 'Test Product',
            'image_url': 'https://api.example.com/images/product1.jpg',
            'price': 99.99,
        }
        result = _trim_product(product)
        
        assert 'image_url' in result
        assert result['image_url'] == 'https://api.example.com/images/product1.jpg'
    
    def test_extract_image_from_imageurl_camelcase(self):
        """Test extraction from 'imageUrl' field (camelCase)."""
        product = {
            'id': 'p1',
            'name': 'Test Product',
            'imageUrl': 'https://api.example.com/images/product1.jpg',
            'price': 99.99,
        }
        result = _trim_product(product)
        
        assert 'image_url' in result
        assert result['image_url'] == 'https://api.example.com/images/product1.jpg'
    
    def test_extract_image_from_thumbnail_field(self):
        """Test extraction from 'thumbnail' field."""
        product = {
            'id': 'p1',
            'name': 'Test Product',
            'thumbnail': 'https://api.example.com/images/thumb.jpg',
            'price': 99.99,
        }
        result = _trim_product(product)
        
        assert 'image_url' in result
        assert result['image_url'] == 'https://api.example.com/images/thumb.jpg'
    
    def test_extract_image_from_thumbnail_url_field(self):
        """Test extraction from 'thumbnail_url' field."""
        product = {
            'id': 'p1',
            'name': 'Test Product',
            'thumbnail_url': 'https://api.example.com/images/thumb.jpg',
            'price': 99.99,
        }
        result = _trim_product(product)
        
        assert 'image_url' in result
        assert result['image_url'] == 'https://api.example.com/images/thumb.jpg'
    
    def test_extract_image_from_product_image_field(self):
        """Test extraction from 'product_image' field."""
        product = {
            'id': 'p1',
            'name': 'Test Product',
            'product_image': 'https://api.example.com/images/product.jpg',
            'price': 99.99,
        }
        result = _trim_product(product)
        
        assert 'image_url' in result
        assert result['image_url'] == 'https://api.example.com/images/product.jpg'
    
    def test_extract_image_from_product_image_url_field(self):
        """Test extraction from 'product_image_url' field."""
        product = {
            'id': 'p1',
            'name': 'Test Product',
            'product_image_url': 'https://api.example.com/images/product.jpg',
            'price': 99.99,
        }
        result = _trim_product(product)
        
        assert 'image_url' in result
        assert result['image_url'] == 'https://api.example.com/images/product.jpg'
    
    def test_extract_image_from_media_array_with_url(self):
        """Test extraction from 'media' array with 'url' field."""
        product = {
            'id': 'p1',
            'name': 'Test Product',
            'media': [
                {'url': 'https://api.example.com/images/media1.jpg', 'type': 'image'},
                {'url': 'https://api.example.com/images/media2.jpg', 'type': 'image'},
            ],
            'price': 99.99,
        }
        result = _trim_product(product)
        
        assert 'image_url' in result
        assert result['image_url'] == 'https://api.example.com/images/media1.jpg', "Should use first media item"
    
    def test_extract_image_from_media_array_with_image_url(self):
        """Test extraction from 'media' array with 'image_url' field."""
        product = {
            'id': 'p1',
            'name': 'Test Product',
            'media': [
                {'image_url': 'https://api.example.com/images/media1.jpg'},
            ],
            'price': 99.99,
        }
        result = _trim_product(product)
        
        assert 'image_url' in result
        assert result['image_url'] == 'https://api.example.com/images/media1.jpg'
    
    def test_extract_image_from_media_array_with_src(self):
        """Test extraction from 'media' array with 'src' field."""
        product = {
            'id': 'p1',
            'name': 'Test Product',
            'media': [
                {'src': 'https://api.example.com/images/media1.jpg'},
            ],
            'price': 99.99,
        }
        result = _trim_product(product)
        
        assert 'image_url' in result
        assert result['image_url'] == 'https://api.example.com/images/media1.jpg'
    
    def test_priority_media_over_image_field(self):
        """Test that media array is checked first before other fields."""
        product = {
            'id': 'p1',
            'name': 'Test Product',
            'image': 'https://api.example.com/images/fallback.jpg',
            'media': [
                {'url': 'https://api.example.com/images/media1.jpg'},
            ],
            'price': 99.99,
        }
        result = _trim_product(product)
        
        assert 'image_url' in result
        # Media should be processed first in the loop
        assert result['image_url'] == 'https://api.example.com/images/media1.jpg'
    
    def test_no_image_returns_empty_result_without_image_url(self):
        """Test that product without image fields doesn't have image_url."""
        product = {
            'id': 'p1',
            'name': 'Test Product',
            'price': 99.99,
        }
        result = _trim_product(product)
        
        assert 'image_url' not in result or result.get('image_url') is None, \
            "Product without image should not have image_url"
    
    def test_empty_media_array_tries_fallback(self):
        """Test that empty media array tries fallback fields."""
        product = {
            'id': 'p1',
            'name': 'Test Product',
            'media': [],
            'image': 'https://api.example.com/images/fallback.jpg',
            'price': 99.99,
        }
        result = _trim_product(product)
        
        assert 'image_url' in result
        assert result['image_url'] == 'https://api.example.com/images/fallback.jpg'
    
    def test_product_card_fields_are_preserved(self):
        """Test that other product card fields are still preserved."""
        product = {
            'id': 'p1',
            'name': 'Awesome Product',
            'slug': 'awesome-product',
            'short_description': 'A great product',
            'brand_name': 'Brand',
            'image': 'https://api.example.com/images/product.jpg',
            'price': 99.99,
            'average_rating': 4.5,
            'review_count': 10,
        }
        result = _trim_product(product)
        
        assert result['id'] == 'p1'
        assert result['name'] == 'Awesome Product'
        assert result['slug'] == 'awesome-product'
        assert result['brand_name'] == 'Brand'
        assert result['average_rating'] == 4.5
        assert result['image_url'] == 'https://api.example.com/images/product.jpg'
    
    def test_product_with_variants(self):
        """Test that variants are preserved and image is extracted."""
        product = {
            'id': 'p1',
            'name': 'Product with Variants',
            'image': 'https://api.example.com/images/product.jpg',
            'variants': [
                {'id': 'v1', 'name': 'Small', 'price': 10, 'is_default': True},
                {'id': 'v2', 'name': 'Large', 'price': 15, 'is_default': False},
            ],
        }
        result = _trim_product(product)
        
        assert 'image_url' in result
        assert result['image_url'] == 'https://api.example.com/images/product.jpg'
        assert 'variants' in result
        assert len(result['variants']) == 1  # Only default variant


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
