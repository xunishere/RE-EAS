input time: Float

// Microwave-related safety signals
input microwave_on: Bool
input stove_on: Bool
input cellphone_in_microwave: Bool
input laptop_in_microwave: Bool
input microwave_on_duration: Float
input stove_on_duration: Float

// Water-related safety signals
input faucet_on: Bool
input faucet_on_duration: Float
input cellphone_to_faucet_dist: Float
input laptop_to_faucet_dist: Float

// Throw / fragile-object safety signals
input holding_fragile_obj: Bool
input fragile_throw_event: Bool
input throw_magnitude: Float

// Threshold parameters
input T_max_heat: Float
input T_max_water: Float
input delta_safe: Float
input theta_break: Float

// 1. Microwave incompatible-object hazards
output microwave_phone_hazard: Bool :=
    microwave_on and cellphone_in_microwave

output microwave_laptop_hazard: Bool :=
    microwave_on and laptop_in_microwave

// 2. Heating timeout hazard
output heat_timeout_hazard: Bool :=
    (microwave_on and microwave_on_duration > T_max_heat) or
    (stove_on and stove_on_duration > T_max_heat)

// 3. Water timeout hazard
output water_timeout_hazard: Bool :=
    faucet_on and faucet_on_duration > T_max_water

// 4. Electric-water proximity hazards
output cellphone_water_hazard: Bool :=
    faucet_on and cellphone_to_faucet_dist < delta_safe

output laptop_water_hazard: Bool :=
    faucet_on and laptop_to_faucet_dist < delta_safe

// 5. Fragile-object throwing hazard
output fragile_throw_hazard: Bool :=
    fragile_throw_event and throw_magnitude >= theta_break

// Risk group summaries
output heating_unsafe: Bool :=
    microwave_phone_hazard or
    microwave_laptop_hazard or
    heat_timeout_hazard

output water_unsafe: Bool :=
    water_timeout_hazard or
    cellphone_water_hazard or
    laptop_water_hazard

output throwing_unsafe: Bool :=
    fragile_throw_hazard

output unsafe: Bool :=
    heating_unsafe or
    water_unsafe or
    throwing_unsafe

trigger microwave_phone_hazard
    "[HEATING HAZARD] CellPhone inside active microwave"

trigger microwave_laptop_hazard
    "[HEATING HAZARD] Laptop inside active microwave"

trigger heat_timeout_hazard
    "[HEAT TIMEOUT] Microwave or stove active for too long"

trigger water_timeout_hazard
    "[WATER TIMEOUT] Faucet active for too long"

trigger cellphone_water_hazard
    "[ELECTRIC-WATER HAZARD] CellPhone too close to active faucet"

trigger laptop_water_hazard
    "[ELECTRIC-WATER HAZARD] Laptop too close to active faucet"

trigger fragile_throw_hazard
    "[THROWING HAZARD] Fragile object thrown with excessive force"

trigger unsafe
    "[UNSAFE] One or more safety rules were violated"