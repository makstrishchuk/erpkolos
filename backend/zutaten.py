"""
LMIV Compliant Ingredient List Generator Module
Author: Senior Python Backend Developer (FoodTech)
Context: EU Regulation 1169/2011 (Lebensmittelinformationsverordnung)
"""

from dataclasses import dataclass, field
from typing import List, Optional, Union
from enum import Enum

# --- Enums & Constants ---

class HydrogenationStatus(Enum):
    NONE = None
    PARTLY = "teilweise gehärtet"
    FULLY = "ganz gehärtet"

# --- Data Structures ---

@dataclass
class Ingredient:
    """
    Represents a raw material or ingredient in a recipe.
    """
    name_de: str
    weight_input: float  # Grams or KG, must be consistent across recipe
    
    # Allergen Management (Art. 21)
    is_allergen: bool = False
    
    # Compound Ingredients (Annex VII Part E)
    sub_ingredients: List['Ingredient'] = field(default_factory=list)
    
    # Additives (Annex VII Part C)
    # Example: additive_class="Konservierungsstoff", name_de="E 202"
    additive_class: Optional[str] = None 
    
    # QUID (Art. 22)
    highlight_percentage: bool = False
    
    # Water Calculation (Annex VII Part A)
    is_added_water: bool = False
    
    # Oils/Fats (Annex VII Part A)
    is_oil_fat: bool = False
    botanical_origin: Optional[str] = None # e.g., "Palm", "Raps"
    hydrogenation: HydrogenationStatus = HydrogenationStatus.NONE

    @property
    def total_weight(self) -> float:
        """Returns the weight of this ingredient."""
        return self.weight_input

@dataclass
class Recipe:
    ingredients: List[Ingredient]
    final_product_weight: float  # Weight after processing (baking/cooking)


# --- Logic Engine ---

class LabelGenerator:
    """
    Engine to process a Recipe object and generate a compliant Zutatenliste string.
    """

    def __init__(self, recipe: Recipe):
        self.raw_ingredients = recipe.ingredients
        self.final_weight = recipe.final_product_weight
        self.total_input_weight = sum(i.weight_input for i in self.raw_ingredients)

    def _calculate_declarable_water(self) -> float:
        """
        Calculates if added water must be declared (Annex VII Part A).
        Formula: Water Input - (Total Input - Final Output).
        Rule: Omit if < 5% of final product weight.
        """
        total_water_input = sum(i.weight_input for i in self.raw_ingredients if i.is_added_water)
        
        # Calculate moisture loss during processing
        moisture_loss = self.total_input_weight - self.final_weight
        
        # Water remaining in the final product derived from added water
        water_remaining = total_water_input - moisture_loss
        
        if water_remaining <= 0:
            return 0.0
            
        percentage_in_final = (water_remaining / self.final_weight) * 100
        
        # The 5% Threshold Rule
        if percentage_in_final < 5.0:
            return 0.0
            
        return water_remaining

    def _format_allergen(self, text: str) -> str:
        """Applies visual emphasis to allergens (Art. 21)."""
        return f"**{text}**"

    def _format_quid(self, ingredient: Ingredient) -> str:
        """Calculates QUID percentage based on input weight (Art. 22)."""
        # Note: QUID is usually calculated on input weight at mixing time.
        percent = (ingredient.weight_input / self.total_input_weight) * 100
        # Formatting: No decimals usually required if > 1%, but keeping 1 decimal for precision
        return f" {percent:.1f}%"

    def _format_compound_ingredient(self, ingredient: Ingredient) -> str:
        """
        Processes sub-ingredients recursively (Annex VII Part E).
        Handles the 2% exemption rule.
        """
        # Calculate percentage of this compound in the final product context
        # Note: Strictly speaking, the 2% rule applies to the finished product.
        percentage_in_final = (ingredient.weight_input / self.final_weight) * 100
        
        is_below_2_percent = percentage_in_final < 2.0
        
        # Sort sub-ingredients by weight (Art. 18)
        sorted_subs = sorted(ingredient.sub_ingredients, key=lambda x: x.weight_input, reverse=True)
        
        formatted_subs = []
        
        for sub in sorted_subs:
            # 2% Rule Logic:
            # If compound is < 2%, we skip sub-ingredients UNLESS they are:
            # 1. Allergens
            # 2. Additives (implied technological function check omitted for simplicity, assuming yes)
            if is_below_2_percent:
                if not (sub.is_allergen or sub.additive_class):
                    continue
            
            # Recursion for nested compounds (rare but possible)
            formatted_subs.append(self._process_single_ingredient_string(sub, is_sub_ingredient=True))

        if not formatted_subs:
            return ""
            
        return f" ({', '.join(formatted_subs)})"

    def _process_single_ingredient_string(self, ing: Ingredient, is_sub_ingredient: bool = False) -> str:
        """
        Formats a single ingredient node into a string.
        """
        display_name = ing.name_de

        # 1. Handle Additives (Annex VII Part C)
        # Format: "Functional Class Name/E-Number"
        if ing.additive_class:
            display_name = f"{ing.additive_class} {display_name}"

        # 2. Handle Oils/Fats (Annex VII Part A)
        if ing.is_oil_fat and ing.botanical_origin:
            # If hydrogenation is specified
            if ing.hydrogenation != HydrogenationStatus.NONE:
                display_name = f"{ing.botanical_origin} ({ing.hydrogenation.value})"
            else:
                display_name = ing.botanical_origin

        # 3. Handle Allergen Emphasis (Art. 21)
        if ing.is_allergen:
            display_name = self._format_allergen(display_name)

        # 4. Handle QUID (Art. 22)
        # Only displayed for top-level ingredients usually, unless specified for sub-ingredients
        if ing.highlight_percentage and not is_sub_ingredient:
            display_name += self._format_quid(ing)

        # 5. Handle Sub-ingredients (Compound Ingredients)
        if ing.sub_ingredients:
            display_name += self._format_compound_ingredient(ing)

        return display_name

    def generate(self) -> str:
        """
        Main execution method to generate the label text.
        """
        processed_list = []

        # 1. Filter out raw added water from the main list (handled separately)
        ingredients = [i for i in self.raw_ingredients if not i.is_added_water]

        # 2. Calculate declarable water
        water_weight = self._calculate_declarable_water()
        if water_weight > 0:
            # Create a virtual ingredient for water
            ingredients.append(Ingredient(name_de="Wasser", weight_input=water_weight))

        # 3. Sort by Weight Descending (Art. 18)
        # Note: Ingredients < 2% could be unordered, but strict sorting is always compliant.
        ingredients.sort(key=lambda x: x.weight_input, reverse=True)

        # 4. Process individual strings
        for ing in ingredients:
            processed_list.append(self._process_single_ingredient_string(ing))

        # 5. Final Assembly
        return "Zutaten: " + ", ".join(processed_list) + "."


# --- Usage Example ---

def run_example():
    # Example: Strawberry Yogurt with Chocolate Chips
    # Total Input: 100 + 20 + 5 + 0.5 = 125.5g
    # Final Weight: 125g (minimal evaporation)
    
    # Compound Ingredient: Chocolate
    chocolate = Ingredient(
        name_de="Schokolade",
        weight_input=5.0, # 5g (approx 4% of total, so sub-ingredients must be listed)
        sub_ingredients=[
            Ingredient(name_de="Zucker", weight_input=2.5),
            Ingredient(name_de="Kakaomasse", weight_input=2.0),
            Ingredient(name_de="Sojalecithin", weight_input=0.1, is_allergen=True, additive_class="Emulgator"),
            Ingredient(name_de="Milchpulver", weight_input=0.4, is_allergen=True)
        ]
    )

    # Compound Ingredient: Fruit Prep (Small amount to test < 2% rule)
    # 1.5g is < 2% of 125g. 
    # Only Allergens/Additives should appear.
    fruit_prep = Ingredient(
        name_de="Fruchtzubereitung",
        weight_input=1.5,
        sub_ingredients=[
            Ingredient(name_de="Erdbeeren", weight_input=1.0), # Should be hidden
            Ingredient(name_de="Zucker", weight_input=0.4),    # Should be hidden
            Ingredient(name_de="E 202", weight_input=0.1, additive_class="Konservierungsstoff") # Must show (Additive)
        ]
    )

    # Main Recipe
    recipe = Recipe(
        final_product_weight=125.0,
        ingredients=[
            Ingredient(name_de="Joghurt", weight_input=100.0, is_allergen=True), # Base
            Ingredient(name_de="Erdbeeren", weight_input=20.0, highlight_percentage=True), # Added fruit
            Ingredient(name_de="Wasser", weight_input=10.0, is_added_water=True), # Added water
            chocolate,
            fruit_prep
        ]
    )

    # Note on Water:
    # Input total = 100 + 20 + 5 + 1.5 + 10 = 136.5
    # Final = 125
    # Loss = 11.5
    # Water remaining = 10 (added) - 11.5 (loss) = -1.5. 
    # Result: Water should NOT appear in list.

    generator = LabelGenerator(recipe)
    label_text = generator.generate()
    
    print("--- Generated Label ---")
    print(label_text)

if __name__ == "__main__":
    run_example()