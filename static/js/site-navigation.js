// site-navigation.js
// Purpose: Handles navigation and content loading across the site, including authenticated fetch requests, 
// protected page loading, branding, and section/submenu management.

const apiUrl = 'https://clubmadeira.io'; // Default API URL, override if needed

// Performs authenticated fetch requests for protected resources, ensuring proper authorization headers.
async function authenticatedFetch(url, options = {}) {
    console.log('authenticatedFetch - Initiating fetch - URL:', url);
    const token = localStorage.getItem('authToken');
    console.log('authenticatedFetch - Token retrieved from localStorage:', token || 'None');
    console.log('authenticatedFetch - Options provided:', JSON.stringify(options));

    if (!token) {
        console.warn('authenticatedFetch - No authentication token found - Redirecting to /');
        toastr.error('No authentication token found. Please log in.');
        window.location.href = '/';
        return null;
    }

    const headers = {
        ...options.headers,
        'Authorization': `Bearer ${token}`,
        'Content-Type': options.body instanceof FormData ? undefined : 'application/json'
    };
    console.log('authenticatedFetch - Request headers constructed:', JSON.stringify(headers));

    const finalOptions = {
        ...options,
        headers: headers
    };
    console.log('authenticatedFetch - Final fetch options:', JSON.stringify(finalOptions));

    try {
        console.log('authenticatedFetch - Sending fetch request to:', url);
        const startTime = Date.now();
        const response = await fetch(url, finalOptions);
        const duration = Date.now() - startTime;
        console.log('authenticatedFetch - Fetch response received - Status:', response.status, 'Duration:', `${duration}ms`);
        console.log('authenticatedFetch - Response headers:', JSON.stringify([...response.headers.entries()]));
        console.log('authenticatedFetch - Response URL:', response.url);

        if (!response.ok) {
            const errorText = await response.text();
            console.error('authenticatedFetch - Fetch failed - Status:', response.status, 'Error text:', errorText);
            throw new Error(`Server returned ${response.status}: ${errorText}`);
        }

        if (response.status === 401) {
            console.warn('authenticatedFetch - Unauthorized response (401) - Clearing token and redirecting to /');
            toastr.error('Session expired. Please log in again.');
            localStorage.removeItem('authToken');
            localStorage.removeItem('userId');
            window.location.href = '/';
            return null;
        }

        console.log('authenticatedFetch - Fetch successful - Response OK');
        return response;
    } catch (error) {
        console.error('authenticatedFetch - Error during fetch - URL:', url, 'Error:', error.message, 'Stack:', error.stack);
        toastr.error(error.message || 'Failed to connect to server');
        return null;
    }
}

// Fetches protected page content for navigation, ensuring cache-busting with timestamps.
async function fetchProtectedPage(url, options = {}) {
    console.log('fetchProtectedPage - Starting fetch - URL:', url);
    const token = localStorage.getItem('authToken');
    console.log('fetchProtectedPage - Token:', token || 'None');
    console.log('fetchProtectedPage - Options:', JSON.stringify(options));
    if (!token) {
        console.warn('fetchProtectedPage - No token found - Redirecting to /');
        toastr.error('No authentication token found. Please log in.');
        window.location.href = '/';
        return null;
    }
    try {
        const timestamp = Date.now();
        const fetchUrl = `${apiUrl}${url}?t=${timestamp}`;
        console.log('fetchProtectedPage - Constructed fetch URL with timestamp:', fetchUrl);
        const startTime = Date.now();
        const response = await fetch(fetchUrl, {
            method: 'GET',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Accept': 'text/html'
            }
        });
        const duration = Date.now() - startTime;
        console.log('fetchProtectedPage - Response received - Status:', response.status, 'Duration:', `${duration}ms`);
        if (!response.ok) {
            const errorText = await response.text();
            console.error('fetchProtectedPage - Fetch failed - Status:', response.status, 'Error text:', errorText);
            throw new Error(`Server returned ${response.status}: ${errorText}`);
        }
        const html = await response.text();
        console.log('fetchProtectedPage - Fetched HTML (first 100 chars):', html.substring(0, 100) + '...', 'Total length:', html.length);
        return html;
    } catch (error) {
        console.error('fetchProtectedPage - Error fetching page - URL:', url, 'Error:', error.message, 'Stack:', error.stack);
        toastr.error(error.message || 'Failed to load protected page');
        return null;
    }
}

// Loads page-specific branding content into a specified container.
async function loadBranding(brandingType, containerId = 'brandingContent') {
    console.log('loadBranding - Starting branding load - Type:', brandingType, 'Container ID:', containerId);
    const defaultContents = {
        'partner': '<h1>Partner Dashboard</h1>',
        'merchant': '<h1>Merchant Dashboard</h1>',
        'community': '<h1>Community Dashboard</h1>',
        'admin': '<h1>Admin Dashboard</h1>',
        'login': '<h1>Login</h1>',
        'signup': '<h1>Signup</h1>'
    };
    const defaultContent = defaultContents[brandingType] || '<h1>Dashboard</h1>';
    console.log('loadBranding - Default content for type:', brandingType, 'is:', defaultContent);

    const container = document.getElementById(containerId);
    console.log('loadBranding - Container element:', container);
    if (!container) {
        console.error('loadBranding - Container not found - ID:', containerId);
        return;
    }

    try {
        console.log('loadBranding - Fetching branding from:', `${apiUrl}/branding`);
        const startTime = Date.now();
        const response = await authenticatedFetch(`${apiUrl}/branding`);
        const duration = Date.now() - startTime;
        if (!response) {
            console.warn('loadBranding - No response from fetch - Using default content - Type:', brandingType);
            container.innerHTML = defaultContent;
            return;
        }
        console.log('loadBranding - Fetch completed - Duration:', `${duration}ms`);
        const data = await response.json();
        console.log('loadBranding - Branding data received:', JSON.stringify(data));
        const brandingContent = data.content || defaultContent;
        console.log('loadBranding - Setting branding content:', brandingContent);
        container.innerHTML = brandingContent;
        console.log('loadBranding - Branding content updated in container:', containerId);
    } catch (error) {
        console.error('loadBranding - Error loading branding - Type:', brandingType, 'Error:', error.message, 'Stack:', error.stack);
        toastr.error(`Error loading ${brandingType} branding: ${error.message}`);
        container.innerHTML = defaultContent;
        console.log('loadBranding - Fallback to default content applied - Container ID:', containerId);
    }
}

// Displays a specific section while hiding others, with optional load callback.
function showSection(sectionId, onSectionLoad = null) {
    console.log('showSection - Starting section display - Section ID:', sectionId);
    console.log('showSection - Callback provided:', typeof onSectionLoad === 'function' ? 'Yes' : 'No');
    const allSections = document.querySelectorAll('.section');
    console.log('showSection - Found sections to hide:', allSections.length);
    allSections.forEach(s => {
        console.log('showSection - Hiding section - ID:', s.id);
        s.classList.remove('active');
        s.style.display = 'none';
    });
    const activeSection = document.getElementById(sectionId);
    console.log('showSection - Target section element:', activeSection);
    if (!activeSection) {
        console.error('showSection - Section not found - ID:', sectionId);
        return;
    }
    activeSection.classList.add('active');
    activeSection.style.display = 'block';
    console.log('showSection - Section activated - ID:', sectionId);
    if (typeof onSectionLoad === 'function') {
        console.log('showSection - Executing onSectionLoad callback for:', sectionId);
        onSectionLoad(sectionId);
    } else {
        console.log('showSection - No callback provided, calling loadSection directly');
        loadSection(sectionId);
    }
    console.log('showSection - Section display completed');
}

// Loads content or configures DOM elements for a specific section based on its ID.
async function loadSection(sectionId) {
    console.log('loadSection - Starting section load - Section ID:', sectionId);

    // Handle static or test sections
    if (['welcome', 'page_visit_test', 'order_test', 'affiliateProgramsIntro', 'userManagementIntro', 'testScriptsIntro', 'referralTestsIntro'].includes(sectionId)) {
        console.log('loadSection - Processing static/test section:', sectionId);
        if (sectionId === 'page_visit_test' || sectionId === 'order_test') {
            const timestampId = sectionId === 'page_visit_test' ? 'pageTimestamp' : 'orderTimestamp';
            const timestampElement = document.getElementById(timestampId);
            console.log('loadSection - Timestamp element for', timestampId, ':', timestampElement);

            if (timestampElement) {
                const timestamp = getCurrentTimestamp(); // From site-request.js
                timestampElement.value = timestamp;
                console.log('loadSection - Set timestamp for', timestampId, 'to:', timestamp);
            } else {
                console.error('loadSection - Timestamp element not found - ID:', timestampId);
            }

            const refererId = sectionId === 'page_visit_test' ? 'pageReferer' : 'orderReferer';
            console.log('loadSection - Populating referer dropdown - ID:', refererId);
            await populateRefererDropdown(refererId); // Page-specific stub
        }
        console.log('loadSection - Static/test section load completed');
        return;
    }

    // Handle category listings
    if (sectionId === 'deal_listings') {
        console.log('loadSection - Loading deal listings');
        await loadCategories(); // From category-management.js
        console.log('loadSection - Deal listings loaded');
        return;
    }

    // Handle entity lists
    if (sectionId === 'merchants') {
        console.log('loadSection - Loading merchants');
        await loadMerchants(); // Page-specific stub
        console.log('loadSection - Merchants loaded');
        return;
    }
    if (sectionId === 'communities') {
        console.log('loadSection - Loading communities');
        await loadCommunities(); // Page-specific stub
        console.log('loadSection - Communities loaded');
        return;
    }
    if (sectionId === 'partners') {
        console.log('loadSection - Loading partners');
        await loadPartners(); // Page-specific stub
        console.log('loadSection - Partners loaded');
        return;
    }

    // Handle configuration sections
    console.log('loadSection - Attempting to load config for section:', sectionId);
    try {
        const fetchUrl = `${window.apiUrl || apiUrl}/config`;
        console.log('loadSection - Fetching config from:', fetchUrl);
        const startTime = Date.now();
        const response = await authenticatedFetch(fetchUrl);
        const duration = Date.now() - startTime;

        if (!response) {
            console.error('loadSection - No response from fetch for config - Section:', sectionId);
            toastr.error('Failed to load section credentials: No response');
            return;
        }
        if (!response.ok) {
            const errorText = await response.text();
            console.error('loadSection - Fetch failed - Status:', response.status, 'Error text:', errorText);
            throw new Error(`Failed to fetch /config: ${response.status} - ${errorText}`);
        }

        const data = await response.json();
        console.log('loadSection - Config data received - Duration:', `${duration}ms`, 'Data:', JSON.stringify(data));
        const config = data.config[sectionId] || {};
        console.log('loadSection - Config for section:', sectionId, 'is:', JSON.stringify(config));

        // Populate fields based on section
        if (sectionId === 'amazon_uk') {
            const elements = {
                amazonAccessKey: 'ACCESS_KEY',
                amazonSecretKey: 'SECRET_KEY',
                amazonAssociateTag: 'ASSOCIATE_TAG',
                amazonCountry: 'COUNTRY'
            };
            Object.entries(elements).forEach(([id, key]) => {
                const el = document.getElementById(id);
                console.log('loadSection - Checking element - ID:', id, 'Element:', el);
                if (el) {
                    el.value = config[key] || '';
                    console.log('loadSection - Set', id, 'to:', el.value);
                } else {
                    console.error('loadSection - Element not found - ID:', id);
                }
            });
        } else if (sectionId === 'ebay_uk') {
            const el = document.getElementById('ebayAppId');
            console.log('loadSection - eBay App ID element:', el);
            if (el) {
                el.value = config.APP_ID || '';
                console.log('loadSection - Set ebayAppId to:', el.value);
            } else {
                console.error('loadSection - Element not found - ID: ebayAppId');
            }
        } else if (sectionId === 'awin') {
            const el = document.getElementById('awinApiToken');
            console.log('loadSection - Awin API Token element:', el);
            if (el) {
                el.value = config.API_TOKEN || '';
                console.log('loadSection - Set awinApiToken to:', el.value);
            } else {
                console.error('loadSection - Element not found - ID: awinApiToken');
            }
        } else if (sectionId === 'cj') {
            const elements = {
                cjApiKey: 'API_KEY',
                cjWebsiteId: 'WEBSITE_ID'
            };
            Object.entries(elements).forEach(([id, key]) => {
                const el = document.getElementById(id);
                console.log('loadSection - Checking element - ID:', id, 'Element:', el);
                if (el) {
                    el.value = config[key] || '';
                    console.log('loadSection - Set', id, 'to:', el.value);
                } else {
                    console.error('loadSection - Element not found - ID:', id);
                }
            });
        } else if (sectionId === 'textmagic') {
            const elements = {
                textmagicUsername: 'USERNAME',
                textmagicApiKey: 'API_KEY'
            };
            Object.entries(elements).forEach(([id, key]) => {
                const el = document.getElementById(id);
                console.log('loadSection - Checking element - ID:', id, 'Element:', el);
                if (el) {
                    el.value = config[key] || '';
                    console.log('loadSection - Set', id, 'to:', el.value);
                } else {
                    console.error('loadSection - Element not found - ID:', id);
                }
            });
        } else if (sectionId === 'tiny') {
            const el = document.getElementById('tinyApiKey');
            console.log('loadSection - Tiny API Key element:', el);
            if (el) {
                el.value = config.API_KEY || '';
                console.log('loadSection - Set tinyApiKey to:', el.value);
            } else {
                console.error('loadSection - Element not found - ID: tinyApiKey');
            }
        }

        console.log('loadSection - Successfully loaded credentials for:', sectionId);
        toastr.success(`Loaded credentials for ${sectionId}`);
    } catch (error) {
        console.error('loadSection - Error loading section credentials - Section:', sectionId, 'Error:', error.message, 'Stack:', error.stack);
        toastr.error(`Error loading credentials: ${error.message}`);
    }
    console.log('loadSection - Section load completed - Section ID:', sectionId);
}

// Toggles submenu visibility for navigation menus.
function toggleSubmenu(submenuId) {
    console.log('toggleSubmenu - Starting toggle - Submenu ID:', submenuId);
    const submenu = document.getElementById(submenuId);
    console.log('toggleSubmenu - Submenu element retrieved:', submenu);
    if (!submenu) {
        console.warn('toggleSubmenu - Submenu element not found - ID:', submenuId);
        return;
    }
    const wasOpen = submenu.classList.contains('open');
    submenu.classList.toggle('open');
    const isOpen = submenu.classList.contains('open');
    console.log('toggleSubmenu - Toggled state - ID:', submenuId, 'Was open:', wasOpen, 'Now open:', isOpen);
    console.log('toggleSubmenu - Toggle completed');
}