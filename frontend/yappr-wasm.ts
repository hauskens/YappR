// WASM loader for yappr-wasm
let wasmModule: any = null;

async function loadWasm() {
    try {
        const wasmUrl = '/static/wasm/yappr_wasm.js';
        const { 
            default: init, 
            greet, 
            add, 
            fibonacci, 
            Counter, 
            hewwo,
            TagCategory,
            highlight_text,
            get_contrast_yiq,
            parse_tag_categories_json,
            serialize_tag_categories,
            validate_tag_category_data,
            process_tag_string,
            convert_timestamps,
            load_tag_categories,
            save_tag_categories,
            render_tag_categories,
            open_add_category_modal,
            edit_category_modal,
            save_category_wasm,
            delete_category_wasm,
            export_tag_categories_wasm,
            import_tag_categories_wasm,
            initialize_chat_timeline_chart,
            update_chat_timeline_interval
        } = await import(wasmUrl);
        
        await init('/static/wasm/yappr_wasm_bg.wasm');
        
        wasmModule = {
            greet,
            add,
            fibonacci,
            Counter,
            hewwo,
            TagCategory,
            highlight_text,
            get_contrast_yiq,
            parse_tag_categories_json,
            serialize_tag_categories,
            validate_tag_category_data,
            process_tag_string,
            convert_timestamps,
            load_tag_categories,
            save_tag_categories,
            render_tag_categories,
            open_add_category_modal,
            edit_category_modal,
            save_category_wasm,
            delete_category_wasm,
            export_tag_categories_wasm,
            import_tag_categories_wasm,
            initialize_chat_timeline_chart,
            update_chat_timeline_interval
        };
        
        console.log('WASM module loaded successfully');
        
        // Example usage - remove in production
        console.log('WASM add(5, 3):', wasmModule.add(5, 3));
        
    } catch (error) {
        console.warn('Failed to load WASM module:', error);
    }
}

// Load WASM when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', loadWasm);
} else {
    loadWasm();
}

// Export for global access
(window as any).yapprWasm = () => wasmModule;

// Export individual functions globally for direct access
(window as any).hewwo = (user: string) => wasmModule?.hewwo(user) || 'WASM not loaded';
(window as any).add = (a: number, b: number) => wasmModule?.add(a, b) || 0;
(window as any).fibonacci = (n: number) => wasmModule?.fibonacci(n) || 0;
(window as any).highlightText = (text: string, searchTerm: string) => wasmModule?.highlight_text(text, searchTerm) || text;
(window as any).getContrastYIQ = (hexColor: string) => wasmModule?.get_contrast_yiq(hexColor) || '#000000';
(window as any).validateTagCategoryData = (jsonString: string) => wasmModule?.validate_tag_category_data(jsonString) || false;
(window as any).processTagString = (tagsText: string) => wasmModule?.process_tag_string(tagsText) || [];
(window as any).serializeTagCategories = (categories: any[]) => wasmModule?.serialize_tag_categories(categories) || '[]';
(window as any).convertTimestamps = () => wasmModule?.convert_timestamps();

// Tag category management functions
(window as any).loadTagCategories = () => wasmModule?.load_tag_categories() || [];
(window as any).saveTagCategories = (categories: any[]) => wasmModule?.save_tag_categories(categories);
(window as any).renderTagCategories = (categories: any[]) => wasmModule?.render_tag_categories(categories);
(window as any).openAddCategoryModal = () => wasmModule?.open_add_category_modal();
(window as any).editCategory = (categoryId: string) => wasmModule?.edit_category_modal(categoryId);
(window as any).saveCategoryWasm = () => wasmModule?.save_category_wasm() || false;
(window as any).deleteCategory = (categoryId: string) => wasmModule?.delete_category_wasm(categoryId);
(window as any).exportTagCategories = () => wasmModule?.export_tag_categories_wasm();
(window as any).importTagCategories = () => wasmModule?.import_tag_categories_wasm();

// Chart functions
(window as any).initializeChatTimeline = () => wasmModule?.initialize_chat_timeline_chart();
(window as any).updateChatTimelineInterval = () => wasmModule?.update_chat_timeline_interval();