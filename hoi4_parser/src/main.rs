use std::collections::HashMap;
use std::fs::File;
use std::io::Write;
use std::env;
use hoi4save::{Hoi4File, PdsDate};
use serde_json;

mod enhanced_country;
use enhanced_country::{EnhancedHoi4Save, DivisionTemplate, Division, Faction, FactionResources, DiplomaticRelation, WarStatistics};

use std::collections::BTreeMap;
use regex::Regex;

fn extract_completed_focuses(save_content: &str) -> BTreeMap<String, Vec<String>> {
    let mut completed_by_country = BTreeMap::new();
    
    // Look for the unique pattern: TAG={\n\t\tinstances_counter=
    // This guarantees we're in the actual country section
    let country_pattern = Regex::new(r"(?m)^\t([A-Z]{3})=\{\n\t\tinstances_counter=").unwrap();
    let completed_regex = Regex::new(r#"completed="([^"]+)""#).unwrap();
    
    // Find all country sections with this unique pattern
    let mut country_matches: Vec<(String, usize)> = Vec::new();
    for cap in country_pattern.captures_iter(save_content) {
        let tag = cap[1].to_string();
        let pos = cap.get(0).unwrap().start();
        country_matches.push((tag, pos));
    }
    
    println!("Found {} countries with instances_counter pattern", country_matches.len());
    
    // Process each country
    for i in 0..country_matches.len() {
        let (country_tag, start_pos) = &country_matches[i];
        
        // Find where this country's section starts (at the TAG={ part)
        let country_def_start = start_pos + 1; // Skip the initial tab
        
        // Find the end of this country's section
        // Start after "TAG={"
        let search_start = country_def_start + country_tag.len() + 2;
        
        // Count braces to find the end of this country's data
        let mut brace_count = 1;
        let mut country_end = search_start;
        
        for (idx, ch) in save_content[search_start..].char_indices() {
            if ch == '{' {
                brace_count += 1;
            } else if ch == '}' {
                brace_count -= 1;
                if brace_count == 0 {
                    country_end = search_start + idx;
                    break;
                }
            }
        }
        
        // Extract this country's entire section
        let country_section = &save_content[country_def_start..country_end];
        
        // Look for focus block within this country's section
        if let Some(focus_start) = country_section.find("\t\tfocus={") {
            // Find the matching closing brace for the focus block
            let focus_content_start = focus_start + 9; // Skip "\t\tfocus={"
            let mut brace_count = 1;
            let mut focus_end = focus_content_start;
            
            for (idx, ch) in country_section[focus_content_start..].char_indices() {
                if ch == '{' {
                    brace_count += 1;
                } else if ch == '}' {
                    brace_count -= 1;
                    if brace_count == 0 {
                        focus_end = focus_content_start + idx;
                        break;
                    }
                }
            }
            
            // Extract completed focuses from this country's focus block
            let focus_content = &country_section[focus_content_start..focus_end];
            let mut completed_focuses = Vec::new();
            
            for completed_cap in completed_regex.captures_iter(focus_content) {
                completed_focuses.push(completed_cap[1].to_string());
            }
            
            if !completed_focuses.is_empty() {
                println!("  {} has {} completed focuses: {:?}", 
                    country_tag, completed_focuses.len(), &completed_focuses);
                completed_by_country.insert(country_tag.clone(), completed_focuses);
            } else if focus_content.contains("completed") {
                println!("  {} has 'completed' in focus but regex didn't match", country_tag);
                // Show a sample for debugging
                if let Some(idx) = focus_content.find("completed") {
                    let sample_start = idx.saturating_sub(20);
                    let sample_end = (idx + 50).min(focus_content.len());
                    println!("    Sample: {:?}", &focus_content[sample_start..sample_end]);
                }
            }
        } else {
            // Try without tabs in case formatting varies
            if country_section.contains("focus={") {
                println!("  {} has focus block but not with expected tab formatting", country_tag);
            }
        }
    }
    
    println!("Total countries with completed focuses: {}", completed_by_country.len());
    
    completed_by_country
}

fn extract_character_names(save_content: &str) -> HashMap<i32, String> {
    let mut character_names = HashMap::new();
    
    // Look for character database entries
    let character_pattern = Regex::new(r#"character=\{\s*id=\{\s*id=(\d+)\s+type=\d+\s*\}\s*[^}]*?name="([^"]+)""#).unwrap();
    
    for cap in character_pattern.captures_iter(save_content) {
        if let Ok(id) = cap[1].parse::<i32>() {
            let name = cap[2].to_string();
            println!("Found character: ID {} -> {}", id, name);
            character_names.insert(id, name);
        }
    }
    
    println!("Extracted {} character names", character_names.len());
    character_names
}

fn extract_nested_block(content: &str, start_keyword: &str) -> Option<String> {
    if let Some(block_start) = content.find(start_keyword) {
        let after_keyword = block_start + start_keyword.len();
        let mut brace_count = 1;
        let mut block_end = after_keyword;

        for (idx, ch) in content[after_keyword..].char_indices() {
            if ch == '{' {
                brace_count += 1;
            } else if ch == '}' {
                brace_count -= 1;
                if brace_count == 0 {
                    block_end = after_keyword + idx;
                    break;
                }
            }
        }

        Some(content[after_keyword..block_end].to_string())
    } else {
        None
    }
}

fn extract_division_templates(save_content: &str) -> HashMap<String, Vec<DivisionTemplate>> {
    let mut templates_by_country: HashMap<String, Vec<DivisionTemplate>> = HashMap::new();

    // Pattern to find division_template blocks
    let template_start = Regex::new(r"division_template=\{").unwrap();
    let id_pattern = Regex::new(r#"id=\{\s*id=(\d+)\s+type=52\s*\}"#).unwrap();
    let name_pattern = Regex::new(r#"name="([^"]+)""#).unwrap();
    let country_pattern = Regex::new(r#"country="([A-Z]{3})""#).unwrap();
    let unit_pattern = Regex::new(r#"(\w+)=\{\s*x=\d+\s+y=\d+\s*\}"#).unwrap();

    for template_match in template_start.find_iter(save_content) {
        let start_pos = template_match.start();

        // Find the end of this template block by counting braces
        let mut brace_count = 1;
        let mut end_pos = template_match.end();

        for (idx, ch) in save_content[template_match.end()..].char_indices() {
            if ch == '{' {
                brace_count += 1;
            } else if ch == '}' {
                brace_count -= 1;
                if brace_count == 0 {
                    end_pos = template_match.end() + idx;
                    break;
                }
            }
        }

        let template_content = &save_content[start_pos..end_pos];

        // Extract template data
        let id = id_pattern.captures(template_content)
            .and_then(|c| c[1].parse::<i32>().ok())
            .unwrap_or(0);

        let name = name_pattern.captures(template_content)
            .map(|c| c[1].to_string())
            .unwrap_or_default();

        let country = country_pattern.captures(template_content)
            .map(|c| c[1].to_string());

        if let Some(country_tag) = country {
            if !name.is_empty() {
                // Extract regiments using proper nested block parsing
                let mut regiments = Vec::new();
                let mut support = Vec::new();

                if let Some(reg_content) = extract_nested_block(template_content, "regiments={") {
                    for cap in unit_pattern.captures_iter(&reg_content) {
                        regiments.push(cap[1].to_string());
                    }
                }

                if let Some(sup_content) = extract_nested_block(template_content, "support={") {
                    for cap in unit_pattern.captures_iter(&sup_content) {
                        support.push(cap[1].to_string());
                    }
                }

                let template = DivisionTemplate {
                    id,
                    name,
                    regiments,
                    support,
                };

                templates_by_country.entry(country_tag).or_default().push(template);
            }
        }
    }

    println!("Extracted division templates for {} countries", templates_by_country.len());
    templates_by_country
}

fn extract_divisions(save_content: &str) -> HashMap<String, Vec<Division>> {
    let mut divisions_by_country: HashMap<String, Vec<Division>> = HashMap::new();

    // Find division blocks - they start with division={ and have a division_template_id
    let division_start = Regex::new(r"division=\{").unwrap();
    let id_pattern = Regex::new(r#"id=\{\s*id=(\d+)\s+type=\d+\s*\}"#).unwrap();
    let template_id_pattern = Regex::new(r#"division_template_id=\{\s*id=(\d+)\s+type=\d+\s*\}"#).unwrap();
    let country_pattern = Regex::new(r#"logical_country="([A-Z]{3})""#).unwrap();
    let location_pattern = Regex::new(r"location=(\d+)").unwrap();
    let name_order_pattern = Regex::new(r#"division_name=\{[^}]*name_order=(\d+)"#).unwrap();

    for div_match in division_start.find_iter(save_content) {
        let start_pos = div_match.start();

        // Find the end of this division block by counting braces
        let mut brace_count = 1;
        let mut end_pos = div_match.end();

        for (idx, ch) in save_content[div_match.end()..].char_indices() {
            if ch == '{' {
                brace_count += 1;
            } else if ch == '}' {
                brace_count -= 1;
                if brace_count == 0 {
                    end_pos = div_match.end() + idx;
                    break;
                }
            }
        }

        let div_content = &save_content[start_pos..end_pos];

        // Only process if it has a division_template_id (actual combat division)
        let template_id = match template_id_pattern.captures(div_content) {
            Some(cap) => cap[1].parse::<i32>().unwrap_or(0),
            None => continue, // Skip if not a proper division
        };

        let id = id_pattern.captures(div_content)
            .and_then(|c| c[1].parse::<i32>().ok())
            .unwrap_or(0);

        let country = country_pattern.captures(div_content)
            .map(|c| c[1].to_string());

        let location = location_pattern.captures(div_content)
            .and_then(|c| c[1].parse::<i32>().ok());

        let name_order = name_order_pattern.captures(div_content)
            .and_then(|c| c[1].parse::<i32>().ok());

        if let Some(country_tag) = country {
            let division = Division {
                id,
                name: name_order.map(|n| format!("#{}", n)),
                template_id,
                location,
            };

            divisions_by_country.entry(country_tag).or_default().push(division);
        }
    }

    println!("Extracted divisions for {} countries", divisions_by_country.len());
    divisions_by_country
}

fn extract_factions(save_content: &str) -> Vec<Faction> {
    let mut factions = Vec::new();

    let faction_start = Regex::new(r"faction=\{").unwrap();
    let name_pattern = Regex::new(r#"name="([^"]+)""#).unwrap();
    let ideology_pattern = Regex::new(r#"ideology=(\w+)"#).unwrap();
    let member_pattern = Regex::new(r#""([A-Z]{3})""#).unwrap();

    for faction_match in faction_start.find_iter(save_content) {
        let start_pos = faction_match.start();

        // Find the end of this faction block
        let mut brace_count = 1;
        let mut end_pos = faction_match.end();

        for (idx, ch) in save_content[faction_match.end()..].char_indices() {
            if ch == '{' {
                brace_count += 1;
            } else if ch == '}' {
                brace_count -= 1;
                if brace_count == 0 {
                    end_pos = faction_match.end() + idx;
                    break;
                }
            }
        }

        let faction_content = &save_content[start_pos..end_pos];

        // Must have a name to be a real faction
        let name = match name_pattern.captures(faction_content) {
            Some(cap) => cap[1].to_string(),
            None => continue,
        };

        let ideology = ideology_pattern.captures(faction_content)
            .map(|c| c[1].to_string())
            .unwrap_or_else(|| "unknown".to_string());

        // Extract members
        let mut members = Vec::new();
        if let Some(members_block) = extract_nested_block(faction_content, "members={") {
            for cap in member_pattern.captures_iter(&members_block) {
                members.push(cap[1].to_string());
            }
        }

        // Extract resources
        let mut resources = FactionResources::default();
        if let Some(extracted_block) = extract_nested_block(faction_content, "extracted={") {
            if let Some(cap) = Regex::new(r"oil=(\d+)").unwrap().captures(&extracted_block) {
                resources.oil = cap[1].parse().unwrap_or(0);
            }
            if let Some(cap) = Regex::new(r"aluminium=(\d+)").unwrap().captures(&extracted_block) {
                resources.aluminium = cap[1].parse().unwrap_or(0);
            }
            if let Some(cap) = Regex::new(r"tungsten=(\d+)").unwrap().captures(&extracted_block) {
                resources.tungsten = cap[1].parse().unwrap_or(0);
            }
            if let Some(cap) = Regex::new(r"steel=(\d+)").unwrap().captures(&extracted_block) {
                resources.steel = cap[1].parse().unwrap_or(0);
            }
            if let Some(cap) = Regex::new(r"chromium=(\d+)").unwrap().captures(&extracted_block) {
                resources.chromium = cap[1].parse().unwrap_or(0);
            }
            if let Some(cap) = Regex::new(r"coal=(\d+)").unwrap().captures(&extracted_block) {
                resources.coal = cap[1].parse().unwrap_or(0);
            }
        }

        // First member is typically the leader
        let leader = members.first().cloned();

        if !members.is_empty() {
            factions.push(Faction {
                name,
                ideology,
                members,
                leader,
                resources,
            });
        }
    }

    println!("Extracted {} factions", factions.len());
    factions
}

fn find_player_faction(factions: &[Faction], player_tag: &str) -> Option<Faction> {
    factions.iter()
        .find(|f| f.members.contains(&player_tag.to_string()))
        .cloned()
}

fn extract_relations_for_country(save_content: &str, country_tag: &str) -> Vec<DiplomaticRelation> {
    let mut relations = Vec::new();

    // Find the country's diplomacy section within the countries block
    // Pattern: look for TAG={ followed by diplomacy data
    let country_section_pattern = format!(r"(?m)^\t{}=\{{\n\t\tinstances_counter=", country_tag);
    let country_start_regex = Regex::new(&country_section_pattern).unwrap();

    if let Some(country_match) = country_start_regex.find(save_content) {
        let start_pos = country_match.start();

        // Find the end of this country's block
        let search_start = country_match.end();
        let mut brace_count = 1;
        let mut country_end = search_start;

        for (idx, ch) in save_content[search_start..].char_indices() {
            if ch == '{' {
                brace_count += 1;
            } else if ch == '}' {
                brace_count -= 1;
                if brace_count == 0 {
                    country_end = search_start + idx;
                    break;
                }
            }
        }

        let country_section = &save_content[start_pos..country_end];

        // Find the diplomacy block within this country, then active_relations within that
        if let Some(diplomacy_block) = extract_nested_block(country_section, "diplomacy={") {
            // Relations are inside active_relations={}
            let relations_block = extract_nested_block(&diplomacy_block, "active_relations={")
                .unwrap_or(diplomacy_block);

            // Now parse each country relation
            let relation_pattern = Regex::new(r"([A-Z]{3})=\{").unwrap();
            let attitude_pattern = Regex::new(r#"attitude="([^"]+)""#).unwrap();
            let opinion_pattern = Regex::new(r"cached_sum=(-?\d+)").unwrap();
            let puppet_pattern = Regex::new(r#"puppet=\{[^}]*autonomy_state="([^"]+)""#).unwrap();
            let market_pattern = Regex::new(r"market_access_rights=\{").unwrap();
            let equipment_pattern = Regex::new(r"equipment_purchase_contract_relation=\{").unwrap();
            let truce_pattern = Regex::new(r#"truce_until="([^"]+)""#).unwrap();

            for relation_match in relation_pattern.find_iter(&relations_block) {
                let rel_start = relation_match.start();
                let other_country = &relations_block[rel_start..rel_start + 3];

                // Find end of this relation block
                let block_start = relation_match.end();
                let mut brace_count = 1;
                let mut rel_end = block_start;

                for (idx, ch) in relations_block[block_start..].char_indices() {
                    if ch == '{' {
                        brace_count += 1;
                    } else if ch == '}' {
                        brace_count -= 1;
                        if brace_count == 0 {
                            rel_end = block_start + idx;
                            break;
                        }
                    }
                }

                let rel_content = &relations_block[rel_start..rel_end];

                let attitude = attitude_pattern.captures(rel_content)
                    .map(|c| c[1].to_string())
                    .unwrap_or_else(|| "unknown".to_string());

                // Skip if no meaningful relation data
                if attitude == "unknown" && !rel_content.contains("puppet=") {
                    continue;
                }

                let opinion = opinion_pattern.captures(rel_content)
                    .and_then(|c| c[1].parse().ok())
                    .unwrap_or(0);

                // Check if this is a puppet relationship
                let puppet_cap = puppet_pattern.captures(rel_content);
                let is_puppet = puppet_cap.is_some();
                let autonomy_level = puppet_cap.map(|c| c[1].to_string());

                // Check if we are their master (first=us, second=them in puppet block)
                let is_master = rel_content.contains(&format!("first=\"{}\"", country_tag))
                    && rel_content.contains("puppet=");

                let has_market_access = market_pattern.is_match(rel_content);
                let has_equipment_contract = equipment_pattern.is_match(rel_content);

                let truce_until = truce_pattern.captures(rel_content)
                    .map(|c| c[1].to_string());

                relations.push(DiplomaticRelation {
                    country: other_country.to_string(),
                    attitude,
                    opinion,
                    is_puppet,
                    is_master,
                    autonomy_level,
                    has_market_access,
                    has_equipment_contract,
                    truce_until,
                });
            }
        }
    }

    println!("Extracted {} relations for {}", relations.len(), country_tag);
    relations
}

fn extract_war_statistics(save_content: &str, country_tag: &str) -> WarStatistics {
    let mut stats = WarStatistics::default();

    // Find the statistics section for this country
    let stats_pattern = format!(r#"\{{ "{}"\s*\{{\s*data=\{{"#, country_tag);
    let stats_regex = Regex::new(&stats_pattern).unwrap();

    if let Some(stats_match) = stats_regex.find(save_content) {
        let start_pos = stats_match.start();

        // Find end of this stats block (it's quite large)
        let search_start = stats_match.end();
        let mut brace_count = 2; // We're already inside two braces
        let mut stats_end = search_start;

        for (idx, ch) in save_content[search_start..].char_indices() {
            if ch == '{' {
                brace_count += 1;
            } else if ch == '}' {
                brace_count -= 1;
                if brace_count == 0 {
                    stats_end = search_start + idx;
                    break;
                }
            }
        }

        let stats_content = &save_content[start_pos..stats_end];

        // Extract various statistics
        if let Some(cap) = Regex::new(r"puppeted_countries=(\d+)").unwrap().captures(stats_content) {
            stats.puppeted_countries = cap[1].parse().unwrap_or(0);
        }
        if let Some(cap) = Regex::new(r"provinces_gained=(\d+)").unwrap().captures(stats_content) {
            stats.provinces_gained = cap[1].parse().unwrap_or(0);
        }
        if let Some(cap) = Regex::new(r"provinces_lost=(\d+)").unwrap().captures(stats_content) {
            stats.provinces_lost = cap[1].parse().unwrap_or(0);
        }
        if let Some(cap) = Regex::new(r"defensive_victories=(\d+)").unwrap().captures(stats_content) {
            stats.defensive_victories = cap[1].parse().unwrap_or(0);
        }
        if let Some(cap) = Regex::new(r"own_casualties=(\d+)").unwrap().captures(stats_content) {
            stats.own_casualties = cap[1].parse().unwrap_or(0);
        }
        if let Some(cap) = Regex::new(r"enemy_casualties=(\d+)").unwrap().captures(stats_content) {
            stats.enemy_casualties = cap[1].parse().unwrap_or(0);
        }
        if let Some(cap) = Regex::new(r"conquered_percentage=(\d+)").unwrap().captures(stats_content) {
            stats.conquered_percentage = cap[1].parse().unwrap_or(0);
        }
        if let Some(cap) = Regex::new(r"hours_at_war=(\d+)").unwrap().captures(stats_content) {
            stats.hours_at_war = cap[1].parse().unwrap_or(0);
        }
    }

    println!("Extracted war statistics for {}", country_tag);
    stats
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().collect();
    
    let save_path = if args.len() > 1 {
        &args[1]
    } else {
        "autosave.hoi4"
    };
    
    let output_path = if args.len() > 2 {
        &args[2]
    } else {
        "../data/game_data.json"
    };
    
    println!("Parsing HOI4 save file: {}", save_path);
    
    if !std::path::Path::new(save_path).exists() {
        println!("Error: Save file '{}' not found!", save_path);
        return Ok(());
    }
    
    let data = std::fs::read(save_path)?;
    let save_content = String::from_utf8_lossy(&data);
    
    // Extract completed focuses before main parsing
    println!("Extracting completed focuses...");
    let completed_focuses = extract_completed_focuses(&save_content);
    
    // Extract character names
    println!("Extracting character names...");
    let character_names = extract_character_names(&save_content);

    // Extract division templates and divisions
    println!("Extracting division templates...");
    let division_templates = extract_division_templates(&save_content);

    println!("Extracting divisions...");
    let divisions = extract_divisions(&save_content);

    println!("Extracting factions...");
    let factions = extract_factions(&save_content);

    let save_file = Hoi4File::from_slice(&data)?;
    let resolver = HashMap::<u16, &str>::new();
    println!("Attempting to parse save file...");
    let save: EnhancedHoi4Save = save_file.parse(resolver)?;
    
    println!("Player country: {}", save.player);
    println!("Date: {}", save.date.game_fmt());
    println!("Total countries: {}", save.countries.len());
    
    // Filter out "id" and "=" tokens from events
    let clean_events: Vec<&String> = save.fired_event_names.iter()
        .filter(|event| *event != "id" && *event != "=")
        .collect();
    
    // Filter for active countries (not default values and can actually do focuses)
    let active_countries: Vec<_> = save.countries.iter()
        .filter(|(_, country)| {
            // Must have non-default stability/war_support values
            let has_activity = country.stability != 0.5 || country.war_support != 0.5;
            
            // Must have either a current focus or be able to do focuses (not just have focus=null)
            let can_do_focuses = match &country.focus {
                Some(focus) => {
                    // If current is Some (has a focus) or current is None but progress exists (just finished)
                    focus.current.is_some() || focus.progress.is_some()
                },
                None => false, // No focus system at all means inactive country
            };
            
            has_activity && can_do_focuses
        })
        .collect();

    // Extract player-specific diplomacy data
    println!("Extracting player diplomacy data...");
    let player_faction = find_player_faction(&factions, &save.player);
    let player_relations = extract_relations_for_country(&save_content, &save.player);
    let player_war_stats = extract_war_statistics(&save_content, &save.player);

    // Create output structure
    let output_data = serde_json::json!({
        "metadata": {
            "player": save.player,
            "date": save.date.game_fmt().to_string(),
            "total_countries": save.countries.len(),
            "active_countries": active_countries.len()
        },
        "diplomacy": {
            "faction": player_faction,
            "relations": player_relations,
            "war_statistics": player_war_stats
        },
        "events": clean_events,
        "countries": active_countries.iter().map(|(tag, country)| {
            let mut country_data = serde_json::to_value(country).unwrap();
            
            // Inject completed focuses if they exist
            if let Some(completed) = completed_focuses.get(tag.as_str()) {
                if let Some(focus) = country_data.get_mut("focus") {
                    focus["completed"] = serde_json::json!(completed);
                }
            }
            
            // Enrich character data with names
            if let Some(politics) = country_data.get_mut("politics") {
                if let Some(parties) = politics.get_mut("parties") {
                    for (_, party) in parties.as_object_mut().unwrap() {
                        if let Some(country_leaders) = party.get_mut("country_leader") {
                            if let Some(leaders_array) = country_leaders.as_array_mut() {
                                for leader in leaders_array {
                                    if let Some(character) = leader.get_mut("character") {
                                        if let Some(id) = character.get("id").and_then(|id| id.as_i64()) {
                                            if let Some(name) = character_names.get(&(id as i32)) {
                                                character.as_object_mut().unwrap().insert("name".to_string(), serde_json::json!(name));
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
            
            let tag_str = tag.as_str();

            // Get division templates for this country
            let templates = division_templates.get(tag_str).cloned().unwrap_or_default();

            // Get divisions for this country
            let country_divisions = divisions.get(tag_str).cloned().unwrap_or_default();

            serde_json::json!({
                "tag": tag_str,
                "data": country_data,
                "division_templates": templates,
                "divisions": country_divisions
            })
        }).collect::<Vec<_>>()
    });
    
    // Write JSON to file
    let mut file = File::create(output_path)?;
    file.write_all(serde_json::to_string_pretty(&output_data)?.as_bytes())?;
    
    println!("Data extracted to: {}", output_path);
    println!("Events: {}", clean_events.len());
    println!("Active countries: {}", active_countries.len());
    
    Ok(())
}