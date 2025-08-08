import json
import copy

class JSONManager:
    """Manage JSON template and operations"""
    
    def __init__(self):
        self.template = {
            "drafter_field": {
                # General Information
                "DocumentProvidedForValuation": " ",
                "StatusOfHolding": "",
                "TypeOfPropertyAsPerDocument": "",
                "PropertySituated": "",
                "FlatOnEachFloor": "",
                "OccupancyPercent": "",
                "ResidualAgeOfProperty(Years)": "",
                "RequestFromAllocatedBy": "",

                #Documented Address
                "PlotNoHouseNo": "",
                "FloorNo": "",
                "BuildingWingName": "",
                "StreetNoRoadName": "",
                "SchemeName": "",
                "VillageCity": "",
                "Pincode": "",
                "Locality": "",
                "District": "",
                "State": "",
                "DocAddressMatchAsPerActualAddress": "",
                "AddressAsPerIdentifierDocs": "",

                #Locality Information
                "ClassOfLocality": "",
                "PropertyUsage": "",
                "ZoneNo": "",
                "Distance from nearest AU Branch": "",
                "AnyNegativeLocality": "",
                "Location-AsPerDLCPortal": "",

                # Property Basic condition
                "Basic amenities available? (Water, Road)": "",
                "Maintenance Levels": "",
                "DeviationForAURemark": "",

                #Setback Info
                "SetbacksAsPerRule-Front": "",
                "SetbacksAsPerRule-Back": "",
                "SetbacksAsPerRule-Side 1": "",
                "SetbacksAsPerRule-Side 2": "",

                # Boundary information
                "EastAsPerDocument(Boundary)": "",
                "WestAsPerDocument(Boundary)": "",
                "NorthAsPerDocument(Boundary)": "",
                "SouthAsPerDocument(Boundary)": "",

                # Dimensions
                "UnitForDimension(Doc)": "ft",
                "EastAsPerDocs(Dimension)": "",
                "WestAsPerDocs(Dimension)": "",
                "NorthAsPerDocs(Dimension)": "",
                "SouthAsPerDocs(Dimension)": ""
            },
            "mobile_field": {
                "Plot No/House No": "",
                "Floor No.": "",
                "Building/Wing Name": "",
                "Street No./Road Name": "",
                "Scheme Name": "",
                "Village/City": "",
                "Nearby Landmark": "",
                "Pincode": "",
                "District": "",
                "State": "",

                "Person Met At Site": "",
                "Occupancy Status": "",
                "Name of Property Owner": "",
                "If rented, Name and No of Occupants": "",
                "Condition of Approach Road": "",
                "Approach /Width of Road to the property": "",
                "Property Type": "",
                "Electricity Meter Status": "",
                "Electricty Meter No": "",
                "Type of Property As per Site": "",
                "Electricity Bill No": "",
                "Elec. Meter No. Matching with Elec. Bill": "",
                "Water Connection Status": "",
                "Gas Line Connection": "",
                "Sewer Connection": "",
                "Other Connection Remark": "",
                "Lift availability": "",
                "Structure Type": "",
                "Nature of Construction": "",
                "Flooring": "",
                "Type of Roof": "",
                "Quality of Construction": "",
                "Age of Property (years)": "",
                "Marketability": "",
                "Stage of Construction": "",
                "No of houses in village (Rural cases)": "",
                "Development in the scheme (in %)": "",
                "Is Property Identified ?": "",
                "Identifier Document": "",
                "Plot Demarcted at Site": "",

                "East - As per Actual(Boundary)": "",
                "West - As per Actual(Boundary)": "",
                "North - As per Actual(Boundary)": "",
                "South - As Per Actual(Boundary)": "",

                "Unit for Dimension (Actual)": "",
                "East - As per Actual(Dimension)": "",
                "West - As per Actual(Dimension)": "",
                "North - As per Actual(Dimension)": "",
                "South - As per Actual(Dimension)": "",

                "Setbacks As per Actual-Front": "",
                "Setbacks As per Actual-Back": "",
                "Setbacks As per Actual-Side 1": "",
                "Setbacks As per Actual-Side 2": "",

                "Local Dealer Name": "",
                "Local Dealer Contact": "",
                "Unit local dealer": "",
                "Min Rate local dealer": "",
                "Max rate local dealer": "",
                "Unit technical": "",
                "Min Rate Technical": "",
                "Max Rate Technical": "",
                "Valuation Remark": "",
        }
    }

    def get_template(self):
        """Get a fresh copy of the JSON template"""
        return copy.deepcopy(self.template)
    
    def save_json(self, data, filepath):
        """Save JSON data to file"""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"💾 JSON saved to: {filepath}")
