export interface Pagination {page:number;page_size:number;total:number;has_more:boolean}
export interface ApiEnvelope<T>{code:number;message:string;data:T;pagination?:Pagination;timestamp:number}
export interface User{user_id:number;username:string;nickname:string;role:string;status:string;phone?:string;email?:string;student_no?:string;profile_complete?:boolean}
export interface Category{category_id:number;name:string;icon:string;sort_order:number;documents:DocCard[]}
export interface DocCard{document_id:number;title:string;summary:string;cover_url:string;category_id:number;category_name?:string;publish_at:string;view_count:number;allow_download:boolean}
export interface DocumentDetail extends DocCard{content:string;source_department:string;document_no:string;effective_date:string;expire_date:string;file_name:string;file_type:string;download_url:string}
export interface Citation{citation_id?:number;source_type:string;document_id?:number;title:string;source_url?:string;snippet?:string;page_no?:number;tool_name?:string;sort_order?:number}
export interface ChatMessage{message_id?:number;role:'USER'|'ASSISTANT';content:string;status?:string;citations?:Citation[];suggestions?:string[];feedback?:{rating:string;status:string};is_grounded?:boolean;created_at?:string}
export interface Session{exsession_id?:number;session_id:number;title:string;last_message_at:string;message_count?:number;status?:string}
